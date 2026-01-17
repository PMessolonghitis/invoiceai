# InvoiceAI - Complete Setup Guide

## What is InvoiceAI?

InvoiceAI is a professional invoice generator SaaS for freelancers and small businesses. It lets users:
- Create beautiful, professional invoices
- Manage clients
- Track payment status
- Download PDFs
- Share invoices via public links

## Revenue Model

| Plan | Price | Target |
|------|-------|--------|
| Free | $0 | Lead generation (5 invoices/month) |
| Starter | $9/mo | Growing freelancers (50 invoices/month) |
| Pro | $19/mo | Power users (unlimited) |

**Goal:** 50-100 paying customers = $450-1900/month

---

## QUICK START (Run Locally First)

### Step 1: Install Python
If you don't have Python installed:
- Download from https://www.python.org/downloads/
- During installation, CHECK "Add Python to PATH"

### Step 2: Open Command Prompt
- Press `Windows + R`
- Type `cmd` and press Enter
- Navigate to the project folder:
```
cd C:\Users\panme\my_project\InvoiceAI
```

### Step 3: Create Virtual Environment
```
python -m venv venv
venv\Scripts\activate
```

### Step 4: Install Dependencies
```
pip install -r requirements.txt
```

Note: WeasyPrint (for PDF generation) requires additional setup on Windows:
- Download GTK3 from: https://github.com/nicokoch/gtk-rs-lgpl/releases
- Add to PATH, or use the alternative below

### Step 5: Create Environment File
```
copy .env.example .env
```

Edit `.env` with Notepad:
```
notepad .env
```

For now, just change SECRET_KEY to any random string:
```
SECRET_KEY=my-super-secret-key-12345
```

### Step 6: Run the Application
```
python app.py
```

### Step 7: Open in Browser
Go to: http://localhost:5000

You should see the InvoiceAI landing page!

---

## DEPLOYMENT TO PRODUCTION

### Option A: Railway (Recommended - Easiest)

Railway offers free hosting with easy deployment.

1. **Create Railway Account**
   - Go to https://railway.app
   - Sign up with GitHub

2. **Deploy the App**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Connect your GitHub and push this code
   - Or use "Deploy from Local" option

3. **Add Environment Variables**
   In Railway dashboard, add:
   - `SECRET_KEY` = (generate a random string)
   - `DATABASE_URL` = (Railway provides this automatically for Postgres)

4. **Get Your URL**
   Railway will give you a URL like: `invoiceai-production.up.railway.app`

5. **Add Custom Domain** (Optional)
   - Buy a domain ($10-15/year from Namecheap, Cloudflare, etc.)
   - Add it in Railway settings

### Option B: Render (Also Free Tier)

1. Go to https://render.com
2. Create account and "New Web Service"
3. Connect GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `gunicorn app:app`
6. Add environment variables

### Option C: DigitalOcean App Platform ($5/month)

More professional, better for production:
1. Create account at digitalocean.com
2. Create new App
3. Connect GitHub
4. Select Python buildpack
5. Add environment variables

---

## SETTING UP STRIPE PAYMENTS

This is how you'll actually collect money.

### Step 1: Create Stripe Account
1. Go to https://stripe.com
2. Sign up and verify your identity
3. Connect your bank account

### Step 2: Create Products
1. Go to Stripe Dashboard > Products
2. Click "Add Product"

**Create Starter Plan:**
- Name: "InvoiceAI Starter"
- Price: $9/month (recurring)
- Click Save and copy the Price ID (starts with `price_`)

**Create Pro Plan:**
- Name: "InvoiceAI Pro"
- Price: $19/month (recurring)
- Copy the Price ID

### Step 3: Get API Keys
1. Go to Stripe Dashboard > Developers > API Keys
2. Copy "Publishable key" (starts with `pk_`)
3. Copy "Secret key" (starts with `sk_`)

### Step 4: Set Up Webhook
1. Go to Stripe Dashboard > Developers > Webhooks
2. Click "Add endpoint"
3. URL: `https://your-domain.com/webhook/stripe`
4. Select events: `customer.subscription.updated`, `customer.subscription.deleted`
5. Copy the Webhook signing secret

### Step 5: Update Environment Variables
```
STRIPE_SECRET_KEY=sk_live_your_key_here
STRIPE_PUBLISHABLE_KEY=pk_live_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_secret_here
STRIPE_PRICE_STARTER=price_starter_id_here
STRIPE_PRICE_PRO=price_pro_id_here
```

**IMPORTANT:** Use `sk_test_` and `pk_test_` keys for testing first!

---

## MARKETING & GETTING CUSTOMERS

### Week 1-2: Foundation

1. **Create Social Profiles**
   - Twitter/X account for InvoiceAI
   - LinkedIn company page
   - ProductHunt upcoming page

2. **SEO Basics**
   - Add meta descriptions to pages
   - Create a simple blog (can add later)
   - Target keywords: "free invoice generator", "invoice maker for freelancers"

### Week 3-4: Launch

1. **ProductHunt Launch**
   - Schedule launch on ProductHunt
   - Write compelling description
   - Get friends to upvote

2. **Reddit Marketing** (FREE)
   Post in these subreddits:
   - r/freelance
   - r/smallbusiness
   - r/SideProject
   - r/Entrepreneur

   Be helpful first, don't spam. Share your tool when relevant.

3. **Indie Hackers**
   - Post on indiehackers.com
   - Share your journey and numbers

### Ongoing: Content Marketing

1. **Write Blog Posts:**
   - "How to Create a Professional Invoice"
   - "Invoice Templates for Freelancers"
   - "Getting Paid Faster: Invoice Tips"

2. **YouTube Tutorial**
   - Screen record using the app
   - Show how easy it is

### Paid Options (When Ready)

1. **Google Ads**
   - Target: "invoice generator", "create invoice online"
   - Budget: Start with $5-10/day

2. **Facebook/Instagram Ads**
   - Target: Freelancers, small business owners
   - Creative: Show the invoice interface

---

## PRICING STRATEGY

### Why This Pricing Works

- **Free tier:** Brings in users who may upgrade
- **$9/month:** Cheap enough that freelancers don't think twice
- **$19/month:** For serious users who need unlimited

### Conversion Expectations

- 100 free users → 5-10 convert to paid (~5-10%)
- Average revenue per paid user: ~$12/month
- Goal: 100 paid users = $1,200/month

---

## MONTHLY COSTS

| Service | Cost |
|---------|------|
| Hosting (Railway free tier) | $0 |
| Domain name | $1/month (annual) |
| Stripe fees | 2.9% + $0.30 per transaction |
| **Total** | ~$1-5/month |

At $1000/month revenue, Stripe takes ~$30. Net profit: ~$965/month.

---

## CHECKLIST

### Before Launch
- [ ] Test all features locally
- [ ] Deploy to production
- [ ] Set up Stripe with real keys
- [ ] Test a real payment (use test card)
- [ ] Set up custom domain

### At Launch
- [ ] Post on ProductHunt
- [ ] Share on Reddit
- [ ] Post on Indie Hackers
- [ ] Tweet about it

### After Launch
- [ ] Monitor for errors
- [ ] Respond to user feedback
- [ ] Add features users request
- [ ] Keep posting content

---

## SUPPORT

If something doesn't work:
1. Check the console for error messages
2. Make sure all environment variables are set
3. Ensure Python dependencies are installed

Common issues:
- **"Module not found"** → Run `pip install -r requirements.txt`
- **"Port in use"** → Change port in app.py or kill the other process
- **"Database error"** → Delete `invoiceai.db` and restart

---

## NEXT STEPS FOR GROWTH

Once you hit $1000/month, consider:

1. **Add Features**
   - Recurring invoices
   - Payment reminders via email
   - Multi-user/team accounts

2. **Integrations**
   - QuickBooks sync
   - Zapier integration
   - Slack notifications

3. **Expand Marketing**
   - Affiliate program
   - Partner with freelance communities
   - Sponsor newsletters

Good luck! 🚀
