
# MobileTimeTracker
marketing dashboard/ data aggregation

## Frontend Stack

The UI uses three CDN libraries loaded in `templates/base.html`:

| Library | Purpose | CDN |
|---|---|---|
| **Tailwind CSS** | Utility-first styling | `cdn.tailwindcss.com` (Play CDN) |
| **Alpine.js 3** | Lightweight interactivity (dropdowns, toggles) | jsDelivr |
| **Chart.js 4** | Animated, responsive data visualizations | jsDelivr |

### Switching from Tailwind Play CDN to a production build

The Play CDN is convenient but shows a console warning in production and
doesn't support tree-shaking. To switch to the Tailwind CLI build:

```bash
# 1. Install Tailwind CLI (one-time)
npm init -y
npm install -D tailwindcss

# 2. Create config (tailwind.config.js)
npx tailwindcss init
# Set content to: ["./templates/**/*.html"]
# Move the custom colors/fonts from the <script> tag in base.html
# into the config file's theme.extend section.

# 3. Create an input CSS file (static/src/input.css)
echo '@tailwind base; @tailwind components; @tailwind utilities;' > static/src/input.css

# 4. Build (run once, or with --watch during dev)
npx tailwindcss -i static/src/input.css -o static/css/tailwind.css --minify

# 5. In base.html, replace the <script src="cdn.tailwindcss.com"> tag with:
#    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
#    and remove the tailwind.config script block.
```

This produces a ~15 KB CSS file with only the classes you actually use.
