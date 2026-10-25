# Launching ConcreteMix AI to the Public Web (Google Cloud)

This guide walks you through deploying **ConcreteMix AI** live on Google Cloud so anyone in the world can access it via a public HTTPS URL (instead of `localhost:8000`).

---

## Method 1: Google Cloud Run (Recommended & Most Cost-Effective)

Google Cloud Run runs your containerized app with automatic HTTPS, free SSL certificates, and **scales down to zero when idle** (practically free within Google Cloud's 2 million requests/month free tier).

### Step 1: Install & Authenticate Google Cloud SDK (gcloud)
1. Download and install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) if you haven't already.
2. In your terminal, authenticate with your Google account:
   ```powershell
   gcloud auth login
   ```
3. Set your Google Cloud Project ID (create one in [Google Cloud Console](https://console.cloud.google.com) if needed):
   ```powershell
   gcloud config set project YOUR_PROJECT_ID
   ```
4. Enable the necessary APIs:
   ```powershell
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
   ```

---

### Step 2: One-Command Build & Deploy
Inside this project directory (`C:\Users\Prakash\.gemini\antigravity\scratch\concretemix-ai`), run:

```powershell
gcloud run deploy concretemix-ai `
  --source . `
  --platform managed `
  --region asia-south1 `
  --allow-unauthenticated `
  --memory 1Gi `
  --cpu 1
```

> **Note on flags:**
> - `--source .`: Automatically packages the project using the included `Dockerfile` and builds it on Google Cloud Build.
> - `--region asia-south1`: Deploys close to Indian civil engineers (Mumbai region). You can also use `us-central1`.
> - `--allow-unauthenticated`: Makes the website publicly accessible to the world without requiring a login.

Once the command finishes, `gcloud` will output your live URL:
```
Service URL: https://concretemix-ai-xxxxxxxx-el.a.run.app
```

---

## Method 2: Deploying via GitHub & Google Cloud Console (No CLI needed)

If you prefer a visual web interface:
1. Push this project folder to a repository on **GitHub** (private or public).
2. Go to **Google Cloud Console** $\rightarrow$ **Cloud Run** $\rightarrow$ Click **Create Service**.
3. Select **Continuously deploy from a repository** (Cloud Build).
4. Connect your GitHub account and select your `concretemix-ai` repo.
5. In **Build Configuration**, choose **Dockerfile** (it will detect `/Dockerfile`).
6. Under **Authentication**, check **Allow unauthenticated invocations**.
7. Click **Create**. Google will build and host your app live with a public `.run.app` address.

---

## Method 3: Instant 1-Click Free Hosting (Render.com)

If you don't have a Google Cloud billing account setup yet and want an immediate live link:
1. Push this folder to GitHub.
2. Go to [Render.com](https://render.com) and log in with GitHub.
3. Click **New +** $\rightarrow$ **Web Service**.
4. Select your repository.
5. Set:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Click **Deploy Web Service** to receive an instant free URL like `https://concretemix-ai.onrender.com`.

---

## Custom Domain Setup (Optional)
To map your own domain (e.g. `www.concretemix.ai`):
1. In Google Cloud Run, click your service $\rightarrow$ **Manage Custom Domains**.
2. Add your domain name and follow the DNS verification instructions to add CNAME/A records.
