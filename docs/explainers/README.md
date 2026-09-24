# Explainer GIFs

Source for `docs/request-flow.gif` and `docs/langchain.gif`: each page is a step-by-step diagram in the app's dark theme.

```bash
npm install puppeteer-core            # uses the local Google Chrome
node render.mjs flow.html flow        # one PNG per step
./mkgif.sh flow ../request-flow.gif 3.6 5
node render.mjs langchain.html lc
./mkgif.sh lc ../langchain.gif 3.8 5
```
