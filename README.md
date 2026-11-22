# 🌾 Kisaan Suvidha 2.0 (किसान सुविधा)
### *Rooted in knowledge. Growing your future.*

A responsive, production-style agricultural decision support platform built with **Python Flask**, **HTML5**, **CSS3**, and **Vanilla JavaScript**, reproducing the UI, layout, typography, and color palette of the official design mockups.

---

## 📸 Key Features & Screen Breakdown

### 1. Authentication Flow
- **Login Screen (`/login`)**: Split-screen design with nature brand panel, mobile & password authentication, support links, and security badges.
- **Registration Screen (`/register`)**: Account creation with farmer name, mobile number, strong password validation, and dynamic State & District dropdowns.
- **OTP Verification Screen (`/verify-otp`)**: 6-box verification code input with auto-cursor advance, 28-second countdown timer, resend button, and Twilio SMS verification badge.

### 2. Main Agricultural Workspace
- **Dashboard (`/dashboard`)**:
  - Top header with location pill (`Punjab / Ludhiana`), bilingual switcher (`English / हिन्दी`), and farmer profile avatar.
  - Kharif Season hero banner card with custom gradient styling.
  - Real-time weather card (`29°C Partly cloudy`, 72% humidity, 8 mm rainfall).
  - Farm snapshot card (`Gurpreet Singh • 4.5 acres • Alluvial soil • Irrigated`).
  - 7 Interactive Action Cards (`01` Crop recommendation, `02` Suitability analysis, `03` Disease detection, `04` KisaanBot, `05` History, `06` Government schemes, `07` Customer support).
- **Crop Recommendation (`/recommendation`)**:
  - Location and growing conditions selector (State, District, Season, Soil Type).
  - **Basic Mode**: Automatically uses typical regional nutrient values for the selected soil type (no soil health card required).
  - **Advanced Mode**: Allows farmers to enter specific Soil Health Card values (Nitrogen, Phosphorus, Potassium, and Soil pH).
  - **ML Recommendation Results (`/recommendation/result`)**: Shows ML Probability (92%), Hybrid Suitability (94/100), Confidence (High), top recommended crop (`Rice (Paddy)`), weather & water needs, 3 progress breakdown bars (Soil 96%, Seasonal 98%, Regional 89%), and alternatives (`Maize 84%`, `Pearl millet 79%`).
- **Crop Suitability Analysis (`/suitability`)**:
  - Analyzes how a specific crop performs against local 7-day weather forecasts.
  - Day-wise suitability cards (Tue 08 Jul to Mon 14 Jul) with Good, Moderate, and Poor status badges.
  - Interactive SVG trend charts for Temperature (°C), Humidity (%), and Daily Rainfall (mm).
  - Agronomic heatwave alert banner (`Watch the heat on 10 July - 36°C with low humidity`).
- **History Log (`/history`)**:
  - Filterable by activity type (All activity, Recommendations, Analyses, Disease scans).
  - Real-time search by crop name or location.
  - Interactive detail modal on clicking `View →`.
- **Government Schemes (`/schemes`)**:
  - Categorized schemes for Income Support (`PM-KISAN ₹6,000`), Crop Insurance (`PMFBY 2% premium`), and Farm Credit (`Kisan Credit Card at 4%`).
  - Direct links to official government portals and instant consultation via KisaanBot.
- **Customer Support (`/support`)**:
  - Support messaging form with automated ticket generation (`#TICK-XXXX`).
  - Integrated FAQ accordion for common farming questions.
- **Profile Settings (`/profile`)**:
  - Farmer personal information, farm acreage, soil type, and irrigation system management.
  - Language preference selector with instant persistence.

---

## 🚀 Additional Required Capabilities

### 1. 🤖 KisaanBot — Global AI Assistant & Embeddable Widget
- **Dedicated Full-Page Assistant (`/kisaanbot`)**:
  - Contextual conversations tailored to the farmer's specific location (`Ludhiana, Punjab`), acreage (`4.5 acres`), and soil profile (`Alluvial, pH 6.5`).
  - Multilingual support: **English**, **Hindi (हिन्दी)**, and **Hinglish**.
  - Speech-to-Text voice recognition via Web Speech API.
  - Quick action suggestion chips (`Why was rice recommended?`, `Water needs`, `Soil pH`, `Govt schemes`).
- **Global Floating Assistant Widget**:
  - Accessible from the bottom-right corner of **every single page** in the application.
  - Minimizable floating drawer with pulse beacon animation and unread tooltip.
- **Embeddable Third-Party Widget (`static/js/kisaanbot-widget.js`)**:
  - Can be embedded into any external portal (Krishi Vigyan Kendra, State Agri Portals, Agro-dealers) via a single script tag:
    ```html
    <script 
      src="http://your-domain.com/static/js/kisaanbot-widget.js" 
      data-api-url="http://your-domain.com/api/kisaanbot/chat" 
      data-language="en">
    </script>
    ```
  - Live embed showcase available at **`/embed-demo`**.

### 2. 🔬 AI Crop Disease Detection (`/disease-detection`)
- **Seamless UI Integration**: Matches the Kisaan Suvidha design system with green card surfaces, typography, and badges.
- **Image Input**: Drag-and-drop dropzone, file picker, and camera capture preview.
- **Interactive Sample Test Suite**: Instant 1-click test buttons for:
  - Rice Blast (*Magnaporthe oryzae*)
  - Tomato Late Blight (*Phytophthora infestans*)
  - Wheat Yellow / Stripe Rust (*Puccinia striiformis*)
  - Cotton Leaf Curl Disease (*CLCuD*)
  - Healthy Paddy Leaf (No pathogen detected)
- **Comprehensive Diagnostic Output**:
  - Pathogen identification & confidence score (e.g. `94.8%`).
  - Severity level (`Action Required`, `Urgent`, `Healthy`).
  - Identified botanical symptoms checklist.
  - Chemical fungicide spray schedules (e.g. *Tricyclazole 75% WP @ 0.6g/L*).
  - Organic, biological, and cultural control remedies (*Pseudomonas fluorescens*, *Neem oil*).
  - Direct integration: 1-click button to consult KisaanBot regarding treatment dosages.
- **Model Hook Architecture**: Clean API endpoint (`/api/disease-detection/diagnose`) architected for PyTorch (`.pt`), ONNX Runtime (`.onnx`), and TensorFlow Lite models.

---

## 🛠 Technology Stack & Architecture

- **Backend**: Python 3.11 with Flask 3.1
- **Frontend**: HTML5, CSS3 (Modern Flexbox & CSS Grid), Vanilla JavaScript (ES6+)
- **Architecture**:
  ```
  Kisaan Suvida 2.0/
  ├── app.py                      # Flask application factory & entrypoint
  ├── routes/                     # Blueprint route controllers
  │   ├── auth_routes.py          # Login, Register, Verify OTP, Logout
  │   ├── main_routes.py          # Dashboard, Profile, Embed Demo
  │   ├── crop_routes.py          # Recommendation & Weather Suitability
  │   ├── disease_routes.py       # AI Crop Disease Detection & API
  │   ├── bot_routes.py           # KisaanBot Chat Page & JSON API
  │   ├── history_routes.py       # Activity history & search
  │   ├── schemes_routes.py       # Government schemes
  │   └── support_routes.py       # Customer support tickets
  ├── services/                   # Modular domain engines
  │   ├── crop_engine.py          # ICAR agronomic calculations & ML suitability
  │   ├── weather_engine.py       # 7-day weather compatibility analysis
  │   ├── disease_engine.py       # Botanical pathology diagnostic catalog & CNN hook
  │   └── kisaanbot_engine.py     # Multilingual AI conversational engine
  ├── data/                       # In-memory realistic repository
  │   └── store.py                # User profile, history, schemes, and tickets
  ├── templates/                  # Jinja2 HTML templates matching the PDF
  │   ├── base.html               # Master layout with sidebar & floating assistant
  │   ├── login.html              # Split-screen login view
  │   ├── register.html           # Farmer registration view
  │   ├── verify_otp.html         # 6-box OTP verification view
  │   ├── dashboard.html          # Main overview dashboard
  │   ├── crop_recommendation.html# Basic/Advanced input form
  │   ├── crop_result.html        # ML recommendation outcome
  │   ├── crop_suitability.html   # 7-day forecast suitability
  │   ├── disease_detection.html  # Dedicated AI disease diagnosis page
  │   ├── kisaanbot.html          # Full-page multilingual chatbot
  │   ├── history.html            # Activity log & detail modals
  │   ├── schemes.html            # Government assistance catalog
  │   ├── support.html            # Farmer support desk
  │   ├── profile.html            # Farm & soil configuration
  │   └── embed_demo.html         # External website widget embed showcase
  └── static/
      ├── css/
      │   ├── main.css            # Design system, layout, typography
      │   ├── auth.css            # Split auth screen styles
      │   ├── components.css      # Cards, badges, buttons, SVG charts
      │   └── widget.css          # Floating assistant widget styles
      └── js/
          ├── main.js             # Core navigation & language management
          └── kisaanbot-widget.js # Standalone embeddable widget script
  ```

---

## 🏃 How to Run Locally

1. **Activate Python environment & install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your database and Twilio credentials
   ```

3. **Set up the MySQL database**:
   ```bash
   mysql -u kisaan_user -p kisaan_suvidha < migrations/001_create_location_tables.sql
   mysql -u kisaan_user -p kisaan_suvidha < migrations/002_create_auth_tables.sql
   ```

4. **Start the application**:
   ```bash
   python app.py
   ```

5. **Open in your browser**:
   - Web Application: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**
   - Dashboard: **[http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)**
   - Login: **[http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)**
   - Register: **[http://127.0.0.1:5000/register](http://127.0.0.1:5000/register)**
   - Forgot Password: **[http://127.0.0.1:5000/forgot-password](http://127.0.0.1:5000/forgot-password)**

---

## 🔐 Authentication Flow

### Login (`/login`) — Password only
- Enter your registered mobile number and password.
- On success, you are redirected to your personalised dashboard.
- **No OTP is sent during login.**
- If the mobile number is not registered, you see: *"No account found with this mobile number."* with options to create an account or try another number.
- If the password is wrong, you see: *"Incorrect password. Please try again."* with a Forgot Password link.

### Signup (`/register`) — OTP verification required
1. Enter full name, mobile number, password, confirm password.
2. Select State, District, Tehsil and Village.
3. Click **Create account & verify mobile**.
4. A 6-digit OTP is sent via Twilio (printed to terminal in development when `OTP_DEBUG=true`).
5. Verify the OTP on the dedicated verification page.
6. Account is created and you are logged in automatically.
- OTP expires after 5 minutes.
- Resend OTP cooldown is 60 seconds.
- Duplicate mobile registrations are blocked.

### Forgot Password (`/forgot-password`) — OTP required
1. Enter your registered mobile number.
2. A 6-digit OTP is sent via Twilio.
3. Verify the OTP, then set a new password.
4. You are redirected to login with a success message.
- The used OTP is invalidated and cannot be reused.

### Development mode
- Set `FLASK_ENV=development` and `OTP_DEBUG=true` to print OTPs to the terminal for local testing.
- OTPs are **never** exposed in production HTML, API responses, or logs.


---

## 🔒 Security & Data Privacy
- Built for Indian farmers with private, secure session storage.
- Adheres to government agricultural extension data guidelines.
