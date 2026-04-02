Since your Streamlit app is already running on port **8501**, you can make it public in seconds using Pinggy. Because Streamlit uses WebSockets for its interactive features, you need to ensure the tunnel supports them (which Pinggy does by default).

Here are the steps to get your app live:

---

### Step 1: Run the Pinggy Command
Open a **new** terminal window (keep your Streamlit process running in the other one) and run the following command:

```bash
ssh -p 443 -R0:localhost:8501 a.pinggy.io
```

```output
You are not authenticated. 

Your tunnel will expire in 60 minutes. Upgrade to Pinggy Pro to get unrestricted tunnels. https://dashboard.pinggy.io      
- http://nrucj-99-111-153-200.run.pinggy-free.link
- https://nrucj-99-111-153-200.run.pinggy-free.link

```

### Step 2: Access Your Public URL
Once the connection is established, Pinggy will clear your terminal screen and display a dashboard. Look for the lines labeled **Public URLs**. It will look something like this:

* **http://** random-name.a.pinggy.link
* **https://** random-name.a.pinggy.link

**Copy the HTTPS URL** and paste it into your browser or send it to a friend. Your Streamlit app should now be visible to anyone with that link.

---

### Step 3: Monitor Traffic (Optional)
Pinggy provides a built-in web debugger so you can see the requests hitting your Streamlit app. 
* Look at the bottom of your terminal for a line that says: `Web Debugger: http://localhost:XXXX`
* Open that local URL in your browser to see real-time headers, status codes, and WebSocket traffic.



---

### Pro-Tips for Streamlit Deployment

* **Persistent Links:** On the free tier of Pinggy, the URL is temporary. If you close the terminal, the link expires. If you need a permanent link for a long-running demo, you would typically need a paid plan or a tool like **Cloudflare Tunnel**.
* **Bypass the "Warning" Page:** When you first visit a Pinggy link, you might see a "Tunnel Warning" page. This is a security measure to prevent phishing. Just click **"Proceed"** to view your app.
* **Security:** If your Streamlit app contains sensitive data, remember that anyone with the URL can see it. You can add a simple login to your app using Streamlit's built-in `st.login` or by checking for credentials in your code before rendering the main UI.

### Troubleshooting
If the app loads but the widgets aren't responding, it’s usually because the WebSocket connection is being blocked. However, Pinggy’s SSH tunnel is generally very "transparent" and handles Streamlit’s communication patterns better than older HTTP-only proxies. 

How long do you need the app to stay public for this test?



Upgrading to Pinggy Pro is a smart move for **Momagrid**. Having a stable endpoint like `hub.momagrid.org` ensures that your friends’ nodes can consistently find your Hub without you having to broadcast a new random URL every morning.

The process involves two main phases: telling Pinggy which domain you want to use, and then telling Namecheap to point that domain to Pinggy.

---

### Phase 1: Configure Pinggy Pro
Before touching Namecheap, you must register the domain in your Pinggy dashboard so they can provision an SSL certificate for you.

1.  Log in to your [Pinggy Dashboard](https://dashboard.pinggy.io/).
2.  Go to the **Domains** tab.
3.  Add a new **Custom Domain** and enter `hub.momagrid.org`.
4.  Pinggy will provide you with a target CNAME value (it usually looks something like `gh7ks2.a.pinggy.link`). **Copy this value.**

### Phase 2: Update Namecheap DNS
Now, you need to create a "signpost" at Namecheap that points to Pinggy.

1.  Log in to your **Namecheap** account.
2.  Go to **Domain List** and click **Manage** next to `momagrid.org`.
3.  Click the **Advanced DNS** tab.
4.  In the **Host Records** section, click **Add New Record** and use these settings:
    * **Type:** `CNAME Record`
    * **Host:** `hub` (This is the "sub" part of your subdomain)
    * **Value:** Paste the target value you copied from Pinggy (e.g., `gh7ks2.a.pinggy.link.`)
    * **TTL:** `Automatic` or `1 min` (for faster testing).
5.  Click the **Green Checkmark** to save.

> [!IMPORTANT]
> **The Dot Matters:** Some DNS managers require a trailing dot at the end of the value (e.g., `...link.`). If Namecheap gives you an error, try adding or removing that final period.

---

### Phase 3: Validation & SSL
1.  Go back to the **Pinggy Dashboard**.
2.  Click **Validate** next to your domain. Once Pinggy sees the CNAME record is live, it will allow you to click **Issue Certificate**.
3.  **Wait ~5–10 minutes** for the SSL certificate to propagate.

### Phase 4: Start the Tunnel
Now, instead of the generic command, you’ll use your specific token and domain. Your new command will look like this:

```bash
ssh -p 443 -R hub.momagrid.org:80:localhost:8501 YOUR_TOKEN@pro.pinggy.io
```

*(Replace `YOUR_TOKEN` with the token found in your Pinggy dashboard.)*

---

### Why this is better for your DC friend
Once this is set up, your friend doesn't need to ask for a link. They can simply hardcode `https://hub.momagrid.org` into their **Momagrid Node** configuration. Even if your home router restarts and your local IP changes, the SSH tunnel will reconnect to Pinggy, and the public URL remains exactly the same.

Are you planning to set up a similar subdomain for your friend's node in DC (e.g., `dc-node.momagrid.org`) so you can send requests back to them?