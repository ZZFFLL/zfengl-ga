# GenericAgent HeroUI

Stage 1 frontend for GenericAgent.

## One-click start (recommended)

macOS / Linux:

```bash
make start
```

Windows:

```cmd
start.cmd
```

If `make` is unavailable, `pnpm heroui-start` does the same job.

These always re-apply the executable bit on `start.command` first, so a
`git pull`, fresh clone, or `chmod 644` reset cannot break the launch.

The browser opens at <http://127.0.0.1:5178> (Vite) and the bridge runs
on port 14169.

## Run pieces individually

```bash
make dev      # Vite only
make bridge   # Python bridge only
make stop     # kill anything on the bridge / UI / stray Vite ports
make status   # show pids on bridge / UI ports
make install  # pnpm install
```

Manual fallback if you don't want to use the Makefile:

```bash
python bridge.py     # in one terminal
pnpm dev             # in another
```

By default the frontend talks to `http://127.0.0.1:14169`. Override with:

```bash
VITE_GA_HEROUI_API_TARGET=http://127.0.0.1:14169 pnpm dev
```

Build the static bundle:

```bash
pnpm build
```

## Why does `start.command` keep losing its +x bit?

`git core.fileMode=true` is set locally in `frontends/heroui/.git/config`
so the executable bit **is** tracked, and `start.command` is committed
as mode `100755`. As a belt-and-braces guard:

1. `start.command` re-applies `chmod +x` to itself at the top — any
   successful run keeps the Finder double-click working next time.
2. `make start` and `pnpm heroui-start` re-apply +x on the whole
   `start.command` / `start.cmd` pair before invoking.

So even if an external `chmod 644`, Finder Get Info, or macOS
quarantine prompt strips +x, the next launch fixes it.
