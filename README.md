# Smart Electrical Fault Detection: local run (Windows, Linux, macOS)
Only Python is needed to run it; the React front end is already built in `web/dist`.
1. `python -m venv venv` then `venv\Scripts\activate` (Windows) or `source venv/bin/activate`
2. `pip install -r requirements.txt`   (add `pip install tensorflow` to compare the neural network too)
3. `python train.py`   (creates the model files, prints RF vs NN macro-F1)
4. `python app.py`     then open http://127.0.0.1:5000
The top bar switches portal for testing; switching asks you to sign in with an account of that role.
The system starts empty. Use Live sensors > Inject fault (or the report wizard) to create tickets.
Demo logins: admin/admin123, officer/officer123, resident/resident123.
Sensor node test: POST /api/predict with header X-Node-Key (default node-secret-123), as in your notebook.
Data is in memory until you set MONGO_URI (MongoDB Atlas), which switches storage automatically.

## Changing the front end (needs Node.js)
`cd web && npm install`, run `npm run dev` (http://localhost:5173, proxies to Flask on :5000), then `npm run build` to refresh `web/dist`.
Before deploying set SECRET_KEY, NODE_KEY and MONGO_URI environment variables.

## Deploying to Render + MongoDB Atlas
1. Push this folder to GitHub (keep `web/dist` committed; model files are rebuilt by the build command).
2. MongoDB Atlas: create a free cluster, a database user, allow network access from anywhere, copy the connection string.
3. Render: New > Blueprint > pick the repo (it reads render.yaml). When asked, enter MONGO_URI, ADMIN_PASSWORD, OFFICER_PASSWORD and RESIDENT_PASSWORD.
   SECRET_KEY and NODE_KEY are generated for you (read NODE_KEY in the Render dashboard to configure sensor nodes).
4. Open the Render URL. Sensor nodes POST to https://<your-url>/api/predict with header X-Node-Key.
Free instances sleep when idle: open the site a few minutes before a presentation.

## Sensor node and SMS
- `python sensor_node.py --url https://YOUR-APP.onrender.com --key NODE_KEY --node kanyama-01` sends readings like a real node (needs only `pip install requests`). `--once earth_fault` sends a single fault for demos.
- SMS uses Africa's Talking. Set AT_USERNAME=sandbox, AT_API_KEY (from the sandbox app) and ALERT_PHONE (a number registered as a simulator number in the sandbox). Sandbox messages appear in the Africa's Talking simulator, not on real phones. Without these variables SMS is only logged. Admin > SMS log lists every attempt.
