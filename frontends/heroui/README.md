# GenericAgent HeroUI

Stage 1 frontend for GenericAgent.

Run the bridge:

```bash
python bridge.py
```

Run the UI:

```bash
pnpm dev
```

By default the frontend talks to `http://127.0.0.1:14169`. Override with:

```bash
VITE_GA_HEROUI_API_TARGET=http://127.0.0.1:14169 pnpm dev
```

Build the static bundle:

```bash
pnpm build
```
