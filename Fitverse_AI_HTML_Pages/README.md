# Fitverse AI — HTML UI prototype

A multi-page, responsive HTML/CSS/JavaScript prototype for Fitverse AI.

## Run locally
1. Extract the ZIP.
2. Open `index.html` in a browser, or use VS Code Live Server.
3. No build step or package installation is required.

## Pages
- `index.html` — landing page
- `login.html`, `signup.html`, `forgot-password.html` — authentication UI
- `onboarding.html` — style preference onboarding
- `dashboard.html` — user dashboard
- `designs.html`, `design-detail.html` — fashion catalogue and design detail
- `tryon.html` — virtual try-on workflow
- `measurements.html` — measurement profile
- `style-intelligence.html` — AI personal stylist chat with FASHN VTON 1.5 virtual try-on split studio
- `wardrobe.html` — saved looks
- `profile.html` — profile and privacy settings

## FASHN VTON 1.5 Integration
The Style Intelligence workspace integrates an interactive split studio featuring [FASHN VTON v1.5](https://huggingface.co/spaces/fashn-ai/fashn-vton-1.5):
- **Conversational AI Stylist**: Guides users on Senator wear, Ankara prints, wedding/Owambe guest styling, corporate attire, and color harmony.
- **1-Click Studio Transfer**: Any recommended look card in the chat can be transferred directly into the fitting studio with `⚡ Try On in Studio`.
- **Fitting Canvas & Live Space**: Test outfits on male/female models or uploaded photos, with direct embedding of the live Hugging Face Space for full MMDiT pixel-space virtual try-on.

## Important prototype limitations
This is frontend-only. Login, Google sign-in, password reset, server-side saving, real AI virtual try-on, automatic body measurement estimation, and AI stylist responses require backend services and/or external APIs. The current forms display demo feedback rather than contacting a server. Sample prices, measurements, and product content are placeholders. Images are loaded from Unsplash URLs and therefore require an internet connection.

The demo saves favourites and measurements in browser local storage. Do not use this prototype to collect real user data until authentication, privacy, storage, consent, and deletion controls are implemented.


## Fashion reference imagery added
The Discover Designs page now includes Ankara examples and Senator-wear reference categories. Openly licensed Ankara images are embedded from Wikimedia Commons, with attribution and license details in `image-sources.html`. Senator-wear cards link to editorial lookbooks; generic placeholder images are used rather than copying photos from those publishers. Prices shown as “Inspiration” are not product prices.

Image sources: https://commons.wikimedia.org/wiki/Category:Ankara_style_clothes_in_Nigeria ; https://www.mynativefashion.com/senator-wear-designs/ ; https://wysemanxclusive.lovable.app/lookbook
