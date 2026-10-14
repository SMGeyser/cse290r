# Lumina

A responsive technology product showcase with a minimal, Apple-inspired design.

## Run

```powershell
npm install
npm start
```

Open [localhost:5173](http://localhost:5173). Install the pinned Three.js dependency once. The server uses Node.js built-ins; set `PORT` to choose another port. All assets and the 3D library are served locally.

```powershell
npm run check
```

## Design

- A slim translucent navigation bar and restrained announcement strip.
- A copper Phone Pro hero, a sky-blue MacBook Air section, and paired Watch and Tablet cards.
- Photorealistic local product renders with transparent backgrounds and detailed metal, glass, and silicone materials.
- A real 3D copper phone with beveled geometry, optical lens textures, studio reflections, and a luminous glass screen.
- Consistent typography, spacing, buttons, icons, and muted supporting copy.
- Responsive layouts, mobile navigation, visible keyboard focus, reduced-motion support, and native dialogs.

## Interactions

Product details open in dialogs. Search filters the four products and links to their sections. The shopping bag supports adding products, quantities, removal, and an empty state. Selections last for the current page session. This product concept has no checkout or real product inventory.

The hero stays pinned for 1.6 viewport heights of scrolling while the phone completes a 360-degree turn. Reverse scrolling reverses the rotation. Rendering stops when the phone is idle, outside the viewport, or the page is hidden. Reduced motion removes the extended scroll stage and displays the phone without rotation. Browsers without WebGL display a static product photograph.

The rendering uses the [Three.js physical materials](https://threejs.org/docs/pages/MeshPhysicalMaterial.html) and a [studio environment](https://threejs.org/docs/pages/RoomEnvironment.html) for reflections.

## Files

- `index.html`: page structure, product sections, and dialogs.
- `styles.css`: design tokens, layout, responsive styles, and dialog styling.
- `app.js`: product details, search, shopping bag, and mobile navigation.
- `phone-scene.js`: 3D model, materials, lighting, scroll progress, and accessibility fallbacks.
- `server.js`: dependency-free local server.
- `assets/phone-real.webp`, `macbook-real.webp`, `watch-real.webp`, `tablet-real.webp`: optimized photorealistic renders.
- Matching `*-real.png` files: full-resolution generated sources with alpha transparency.
- `assets/realistic-image-prompts.json`: prompts and built-in image-generation provenance.
- The original product SVGs are retained as earlier artwork.
- `preview-desktop.jpg`: desktop hero.
- `preview-mobile.jpg`: mobile preview.
- `preview-hero.jpg`: desktop hero preview.
- `preview-phone-front.jpg`: the phone's front view partway through its turn.
- `preview-products.jpg`: realistic Watch and Tablet product cards.

Existing assets from the earlier donkey concept are retained but are unused.

## Verification

JavaScript syntax checks passed. Browser checks covered product details, adding and removing bag items, search filtering and empty results, mobile navigation, Escape dismissal, and focus restoration. Layouts were checked at 1280, 768, 390, and 320 pixels wide with no horizontal overflow. The browser reported no console errors during verification.

The updated scene was checked on desktop and mobile for scroll-linked rotation, reverse scrolling, the complete turn, sticky positioning, reload position, and release into the next section. New image alpha channels were verified, and all four product renders loaded successfully. The generated PNG sources total about 6.8 MB; the four served WebP images total 478,884 bytes.

