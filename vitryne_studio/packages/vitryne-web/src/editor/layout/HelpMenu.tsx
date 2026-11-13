// SPDX-License-Identifier: AGPL-3.0-or-later

import { BookOpen, CircleHelp } from "lucide-react";
import type { ComponentType } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DOCS_URL } from "@/links";

/** The documentation, feedback and the source code, in the top bar and on the start screen. */
export function HelpMenu() {
  const links: [string, string, ComponentType][] = [
    ["Documentation", DOCS_URL, BookOpen],
  ];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Help and feedback">
          <CircleHelp />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        {links.map(([label, href, Icon]) => (
          <DropdownMenuItem key={href} asChild>
            <a href={href} target="_blank" rel="noreferrer">
              <span className="grow">{label}</span>
              <Icon />
            </a>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
