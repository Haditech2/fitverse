# Fitverse AI — Intelligent Fashion & FASHN VTON 1.5 Studio (Django)

Fitverse AI is a web application combining Nigerian & African bespoke fashion styling (Senator wear, Ankara prints, Agbada sets, and corporate tailoring) with **FASHN VTON 1.5** neural virtual try-on, built with **Django 6.1**.

---

## ⚡ Tech Stack & Architecture

- **Backend**: Python 3.12, Django 6.1
- **Database**: SQLite (ORM models for `Design`, `Category`, `UserMeasurement`, `SavedLook`, `Favorite`, `VirtualTryOn`)
- **Virtual Try-On Model**: [fashn-ai/fashn-vton-1.5](https://huggingface.co/spaces/fashn-ai/fashn-vton-1.5) (Multimodal Diffusion MMDiT in pixel space)
- **Frontend**: Django Templates (DTL), Vanilla CSS, Responsive Grid & Flexbox, JavaScript

---

## 🚀 Quick Start

Install the backend dependencies first:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

### Configure Gemini safely

Copy `.env.example` to `.env`, then open `.env` and paste your Gemini key after
`GEMINI_API_KEY=`. The `.env` file is ignored by Git and the key is only read
by the Django server; it is never sent to the browser.

```powershell
Copy-Item .env.example .env
notepad .env
```

Keep the key blank until you have created one at
[Google AI Studio](https://aistudio.google.com/apikey). Restart Django after
changing `.env`.

The first try-on request uses the public Hugging Face Space
`fashn-ai/fashn-vton-1.5`. If the Space requires authentication, set
`HF_TOKEN` in the environment. The token stays server-side and is never sent
to the browser. Uploaded person photos are sent to the Hugging Face Space for
inference; add consent and retention controls before using this with real
customer data.

### Configure Bodygram (optional)

Measurements can be estimated automatically from a front photo and a right-side
photo with the [Bodygram Platform API](https://docs.bodygram.com/platform). Sign up
free at [platform.bodygram.com](https://platform.bodygram.com) (5 free scans), then
copy the **Organization ID** and **API Key** from your account page into `.env`:

```bash
BODYGRAM_ORG_ID=your-org-id
BODYGRAM_API_KEY=your-api-key
```

The key stays server-side. Photos are sent to Bodygram for estimation, and a copy of
both photos is saved on the measurement profile so you can see which images produced
the scan; a **Delete photos** button removes them at any time. Each successful estimate
uses one scan credit, so the page warns before scanning. The panel fills the manual form
with the returned measurements and shows body composition (body-fat percentage, skeletal
muscle mass) when Bodygram returns it. Without these values the measurements page still
works in manual mode and the scan endpoint returns a clear "not configured" message.

Every scan returns Bodygram's full measurement set (about 35 values). The measurements
page lists all of them, grouped into circumferences, widths/depths, lengths, and
heights, and highlights the seven that feed your tailoring profile. The full set and
the body composition are stored on the measurement profile.

Bodygram also returns a high-resolution `.obj` body model and a posture reading with
each scan. The page renders the model in an interactive 3D viewer (drag to rotate,
scroll to zoom, **Reset view**) using a locally vendored three.js r147 build — no CDN
request. The avatar is sliced around the bust, waist, hip, upper arm, thigh, and calf,
and each slice becomes a teal girth band labelled with its measured value on a dashed
leader line, mirroring Bodygram's own scan view. The page also shows head, shoulder,
and pelvis tilt from the front photo plus back and neck lean from the side photo. The
model and posture are stored with the scan, so they reappear after a reload. The avatar
is saved once per scan and shared across profiles.

Below the viewer, a card grid shows each measurement with its own thumbnail: the model
is re-rendered from a tight camera at the measured height (waist, bust, wrist, knee …)
with the band on the body, and lengths are drawn as dashed teal spans along the arm,
leg, or spine. Bodygram's API does not return these per-measurement images — only the
`.obj` model, numbers, composition, and posture — so the thumbnails are rendered
client-side from the stored avatar with three.js. They need no extra scan credits.

Reading an existing scan (`GET /api/orgs/{ORG_ID}/scans/{SCAN_ID}`) does **not** consume
quota, so you can refresh a profile from a past scan at any time:

```bash
python manage.py refresh_bodygram_scan            # latest saved scan
python manage.py refresh_bodygram_scan scan_abc123
```

### 1. Run Migrations
```bash
python manage.py migrate
```

### 2. Seed Initial Fashion Catalog & Categories
Populate the database with pre-configured Senator, Ankara, Agbada, and formal designs:
```bash
python manage.py seed_data
```

### 3. Start Development Server
```bash
python manage.py runserver
```
Visit **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your browser.

---

## 🧭 Page Routes & Features

| Route | View | Description |
|---|---|---|
| `/` | `home` | Modern landing page with hero, African fashion features, and trust strip |
| `/dashboard/` | `dashboard` | User workspace with quick links and personalized recommendations |
| `/designs/` | `designs_view` | Fashion catalog with category filters and keyword search |
| `/designs/<slug>/` | `design_detail_view` | Design details with fabric, silhouette, styling advice, and try-on trigger |
| `/style-intelligence/` | `style_intelligence_view` | **Interactive Split Studio**: Conversational AI Stylist on the left + FASHN VTON 1.5 Virtual Try-On Studio on the right |
| `/tryon/` | `tryon_view` | Virtual fitting room canvas with model presets and photo upload |
| `/measurements/` | `measurements_view` | Tailoring profile recording chest, waist, hips, sleeve, inseam in cm/inches, with optional Bodygram photo estimation, 3D body model, and posture reading |
| `/wardrobe/` | `wardrobe_view` | Saved favorites and virtual try-on history |
| `/profile/` | `profile_view` | User profile and account preferences |
| `/admin/` | `admin.site.urls` | Django administrative interface |

---

## 🔌 API Endpoints

- `POST /api/stylist/chat/` — Conversational fashion stylist engine with African fashion knowledge base and dynamic look recommendations.
- `POST /api/vton/tryon/` — Neural try-on session pipeline.
- `POST /api/measurements/save/` — Saves user measurements to the database.
- `POST /api/measurements/bodygram/` — Estimates measurements from a front and right-side photo via the Bodygram Platform API, saves the tailoring fields, the full measurement set, body composition, 3D avatar, posture reading, and scan photos to the user profile.
- `POST /api/measurements/bodygram/photos/delete/` — Deletes the stored scan photos from the profile (the scan results and 3D model stay).
- `POST /api/favorite/toggle/` — Toggles saved designs in user wardrobe.
- `POST /api/looks/save/` — Stores generated virtual try-ons.

### AI provider fallback

`POST /api/vton/tryon/` attempts the configured provider (`AI_PROVIDER`, `gemini` by
default) and automatically retries through FASHN VTON 1.5 if that call fails. Successful
responses report the engine used as `"provider": "gemini" | "fashn"`. If both providers
fail, the endpoint returns HTTP 503 with the combined error, which the fitting studio shows
inline beneath the generate button. Set `AI_PROVIDER=fashn` to skip the Gemini attempt
entirely (useful when the Gemini key has no image quota).

---

## 🎨 Image Sources & Transparency
All Ankara and cultural fashion imagery are openly licensed via Wikimedia Commons (CC BY-SA 4.0) and Unsplash. Full attributions are listed on `/sources/`.
