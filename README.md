# Regulatory Scraper & Briefing Pipeline

An automated system monitoring Philippine regulatory bodies (BIR, IC, SEC) to deliver plain-English executive briefings for insurance and brokerage operations.

## Architecture
Built using Python 3.11+, GitHub Actions, Google Sheets (Configuration), OpenAI (Briefing Summaries), and SMTP/Gmail (Notification Delivery).

## Setup Instructions (Local)

1. **Prerequisites:** Install Python 3.11 or newer and Git.
2. **Virtual Environment Setup:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
