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

The first try-on request uses the public Hugging Face Space
`fashn-ai/fashn-vton-1.5`. If the Space requires authentication, set
`HF_TOKEN` in the environment. The token stays server-side and is never sent
to the browser. Uploaded person photos are sent to the Hugging Face Space for
inference; add consent and retention controls before using this with real
customer data.

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
| `/measurements/` | `measurements_view` | Tailoring profile recording chest, waist, hips, sleeve, inseam in cm/inches |
| `/wardrobe/` | `wardrobe_view` | Saved favorites and virtual try-on history |
| `/profile/` | `profile_view` | User profile and account preferences |
| `/admin/` | `admin.site.urls` | Django administrative interface |

---

## 🔌 API Endpoints

- `POST /api/stylist/chat/` — Conversational fashion stylist engine with African fashion knowledge base and dynamic look recommendations.
- `POST /api/vton/tryon/` — Neural try-on session pipeline.
- `POST /api/measurements/save/` — Saves user measurements to the database.
- `POST /api/favorite/toggle/` — Toggles saved designs in user wardrobe.
- `POST /api/looks/save/` — Stores generated virtual try-ons.

---

## 🎨 Image Sources & Transparency
All Ankara and cultural fashion imagery are openly licensed via Wikimedia Commons (CC BY-SA 4.0) and Unsplash. Full attributions are listed on `/sources/`.
