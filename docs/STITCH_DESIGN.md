# Student Marketplace — Plum & Apricot UI Design

The frontend redesign adopts the **Plum & Apricot** design theme: a warm off-white canvas, deep plum (`#542644`) primary actions, apricot (`#F16529`) accents, Manrope headings, and Inter interface text.

The design was developed from a visual mockup and adapted into the existing Flask + Jinja2 template architecture. An earlier teal Campus Editorial theme was superseded by this direction.

The shared styles are in `frontend/static/marketplace.css`: plum `#542644` actions, apricot `#F16529` accents, warm `#FAF9F6` canvas, `#FBF9F7` sidebar, white surfaces, Manrope headings and Inter interface text. The desktop frame retains the 256 px sidebar, 64 px topbar, 32 px page gutters and lifestyle photo hero. The catalog now spans the available width with four product columns, three on smaller desktops and two on tablets/phones. A horizontal category filter replaces the category dropdown, and listing creation lives on `/sell`. Community widgets, Workspace/Student Listings labels and the hero statistics overlay have been removed.

The HTML was adapted into Jinja views, keeping the existing Flask URLs, database records, authorization, CSRF tokens, file uploads, ratings and checkout behavior. Sidebar admin visibility follows the actual account role. Product and cart counts come from the database; no sample user identity, unread count or fictitious navigation destinations from the static mockup are used.

The existing Kazakh / Russian / English localization also covers the new text. Language switching keeps the current route, filters and fragment. Images, SVG icons and fonts are served locally; Tailwind and the Lucide JavaScript CDN from the export are not runtime dependencies. Font licenses are beside the font assets; SVG icon attribution is in `frontend/static/icons-LICENSE.txt`.

Local sample product photos are mapped in `backend/catalog_images.py` and credited in `frontend/static/images/products/credits.json` and `/photo-credits`. Uploaded images take precedence in the catalog, product detail, cart, promoted items and listing manager. Samples never create or modify `product_photos` records.

On 26 November 2026, the 20 sample photographs were replaced with a curated Pexels selection: linen, kraft paper, warm wood, cream backdrops and muted textiles. Photos were reviewed together at the catalog's 4:5 crop; the kettle photograph was cropped closer to the product. All files are local JPEGs, with photographer and source links retained in the credits manifest. The hero and user-uploaded photos were preserved.
