// Local project storage for the Fitverse Studio development build.
// The editor keeps its normal CloudBackend contract; projects and binary parts live in IndexedDB.
import {
  CloudError,
  type CloudBackend,
  type CloudUser,
  type Manifest,
  type ProjectRow,
  type ProjectSummary,
  type Usage,
} from "./backend";

const OWNER: CloudUser = { id: "fitverse-local", email: null, anonymous: false };
const DATABASE = "fitverse-studio-projects";

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("projects"))
        db.createObjectStore("projects", { keyPath: "id" });
      if (!db.objectStoreNames.contains("parts"))
        db.createObjectStore("parts", { keyPath: "name" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function operation<T>(
  db: IDBDatabase,
  store: "projects" | "parts",
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const request = run(tx.objectStore(store));
    tx.oncomplete = () => resolve(request.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export class LocalBackend implements CloudBackend {
  private constructor(private readonly db: IDBDatabase) {}

  static async connect(): Promise<LocalBackend> {
    return new LocalBackend(await openDatabase());
  }

  onUser(listener: (user: CloudUser | null) => void): () => void {
    listener(OWNER);
    return () => undefined;
  }

  user(): CloudUser {
    return OWNER;
  }

  async ensureUser(): Promise<CloudUser> {
    return OWNER;
  }

  private async row(id: string): Promise<ProjectRow> {
    const row = await operation<ProjectRow | undefined>(
      this.db,
      "projects",
      "readonly",
      (store) => store.get(id),
    );
    if (!row || row.owner !== OWNER.id)
      throw new CloudError("Project not found", "notfound");
    return row;
  }

  async listProjects(): Promise<ProjectSummary[]> {
    const rows = await operation<ProjectRow[]>(
      this.db,
      "projects",
      "readonly",
      (store) => store.getAll(),
    );
    return rows
      .filter((row) => row.owner === OWNER.id)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .map(({ id, name, bytes, revision, updatedAt, thumbnail, shared }) => ({
        id,
        name,
        bytes,
        revision,
        updatedAt,
        thumbnail,
        shared,
      }));
  }

  getProject(id: string): Promise<ProjectRow> {
    return this.row(id);
  }

  async getSharedProject(id: string): Promise<ProjectRow> {
    const row = await this.row(id);
    if (!row.shared) throw new CloudError("Project is private", "notfound");
    return row;
  }

  async insertProject(project: {
    name: string;
    manifest: Manifest;
    bytes: number;
    thumbnail?: string | null;
  }): Promise<ProjectRow> {
    const row: ProjectRow = {
      ...project,
      id: crypto.randomUUID(),
      owner: OWNER.id,
      revision: 1,
      updatedAt: new Date().toISOString(),
      thumbnail: project.thumbnail ?? null,
      shared: false,
    };
    await operation(this.db, "projects", "readwrite", (store) => store.put(row));
    return row;
  }

  async updateProject(
    id: string,
    revision: number,
    project: { name: string; manifest: Manifest; bytes: number },
  ): Promise<ProjectRow | null> {
    let row: ProjectRow;
    try {
      row = await this.row(id);
    } catch {
      return null;
    }
    if (row.revision !== revision) return null;
    const updated: ProjectRow = {
      ...row,
      ...project,
      revision: revision + 1,
      updatedAt: new Date().toISOString(),
    };
    await operation(this.db, "projects", "readwrite", (store) =>
      store.put(updated),
    );
    return updated;
  }

  async deleteProject(id: string): Promise<void> {
    await this.row(id);
    await operation(this.db, "projects", "readwrite", (store) =>
      store.delete(id),
    );
  }

  async setThumbnail(id: string, sha256: string): Promise<void> {
    const row = await this.row(id);
    await operation(this.db, "projects", "readwrite", (store) =>
      store.put({ ...row, thumbnail: sha256 }),
    );
  }

  async setShared(id: string, shared: boolean): Promise<void> {
    const row = await this.row(id);
    await operation(this.db, "projects", "readwrite", (store) =>
      store.put({ ...row, shared }),
    );
  }

  private own(name: string): boolean {
    return name.startsWith(`${OWNER.id}/`);
  }

  async hasPart(name: string): Promise<boolean> {
    if (!this.own(name)) return false;
    return !!(await operation(
      this.db,
      "parts",
      "readonly",
      (store) => store.getKey(name),
    ));
  }

  async uploadPart(
    name: string,
    bytes: ArrayBuffer,
    mediaType: string,
  ): Promise<void> {
    if (!this.own(name)) throw new CloudError("Part owner mismatch");
    await operation(this.db, "parts", "readwrite", (store) =>
      store.put({ name, bytes, mediaType }),
    );
  }

  async downloadPart(name: string): Promise<ArrayBuffer> {
    if (!this.own(name)) throw new CloudError("Part owner mismatch");
    const part = await operation<{ bytes: ArrayBuffer } | undefined>(
      this.db,
      "parts",
      "readonly",
      (store) => store.get(name),
    );
    if (!part) throw new CloudError("Project part is missing", "damaged");
    return part.bytes;
  }

  async listParts(): Promise<string[]> {
    const keys = await operation<IDBValidKey[]>(
      this.db,
      "parts",
      "readonly",
      (store) => store.getAllKeys(),
    );
    return keys.map(String).filter((name) => this.own(name));
  }

  async removeParts(names: string[]): Promise<void> {
    await Promise.all(
      names.filter((name) => this.own(name)).map((name) =>
        operation(this.db, "parts", "readwrite", (store) =>
          store.delete(name),
        ),
      ),
    );
  }

  async unusedParts(): Promise<string[]> {
    const rows = await operation<ProjectRow[]>(
      this.db,
      "projects",
      "readonly",
      (store) => store.getAll(),
    );
    const used = new Set(
      rows.flatMap((row) => [
        ...row.manifest.parts.map((part) => `${row.owner}/${part.sha256}`),
        `${row.owner}/${row.thumbnail}`,
      ]),
    );
    return (await this.listParts()).filter((name) => !used.has(name));
  }

  async usage(): Promise<Usage> {
    const estimate = await navigator.storage.estimate();
    return {
      usedBytes: estimate.usage ?? 0,
      quotaBytes: estimate.quota ?? 0,
      projects: (await this.listProjects()).length,
      maxProjects: 1000,
    };
  }

  async deleteUser(): Promise<void> {
    await Promise.all([
      operation(this.db, "projects", "readwrite", (store) => store.clear()),
      operation(this.db, "parts", "readwrite", (store) => store.clear()),
    ]);
  }
}
