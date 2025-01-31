from flask import Flask, render_template, request, jsonify, send_file
import os
import time
import sqlite3
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from fpdf import FPDF

app = Flask(__name__)

# Paths for Chrome and Chromedriver inside Docker
CHROME_PATH = "/usr/bin/chromium"
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"

# Selenium WebDriver Setup
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")  # Needed inside Docker
chrome_options.add_argument("--disable-dev-shm-usage")  # Prevent crashes
chrome_options.binary_location = CHROME_PATH  # Set Chrome binary path

DB_FILE = "ebay_listings.db"

def init_db():
    """Create the SQLite database and table if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            condition TEXT,
            seller_name TEXT,
            seller_feedback_score TEXT,
            listing_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_webdriver():
    """Initialize Selenium WebDriver."""
    service = Service(CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_ebay_listing(url):
    """Scrapes an eBay listing for title, price, condition, seller info, and feedback score."""
    driver = get_webdriver()
    driver.get(url)
    time.sleep(3)  # Allow JavaScript to load

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    try:
        title = soup.find("h1", {"class": "x-item-title__mainTitle"}).text.strip()
    except AttributeError:
        title = "Not Found"

    try:
        price = soup.find("span", {"itemprop": "price"}).text.strip()
    except AttributeError:
        price = "Not Found"

    try:
        condition = soup.find("div", {"class": "x-item-condition-text"}).text.strip()
    except AttributeError:
        condition = "Not Found"

    try:
        seller_name = soup.find("span", {"class": "ux-textspans ux-textspans--BOLD"}).text.strip()
    except AttributeError:
        seller_name = "Not Found"

    try:
        feedback_score = soup.find("span", {"class": "ux-textspans"}).text.strip()
    except AttributeError:
        feedback_score = "Not Found"

    return {
        "title": title,
        "price": price,
        "condition": condition,
        "seller_name": seller_name,
        "seller_feedback_score": feedback_score,
        "listing_url": url
    }

def save_to_db(data):
    """Inserts scraped listing into the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO listings (title, price, condition, seller_name, seller_feedback_score, listing_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data["title"], data["price"], data["condition"], data["seller_name"], data["seller_feedback_score"], data["listing_url"]))
    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def index():
    """Main page to enter URLs and view listings."""
    if request.method == "POST":
        ebay_url = request.form.get("ebay_url")
        listing_data = get_ebay_listing(ebay_url)
        save_to_db(listing_data)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, price, seller_name FROM listings")
    listings = c.fetchall()
    conn.close()

    return render_template("index.html", listings=listings)

@app.route("/json")
def get_json():
    """Returns all data in JSON format."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM listings")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route("/export_pdf", methods=["POST"])
def export_pdf():
    """Exports selected entries as a PDF."""
    selected_ids = request.form.getlist("selected_ids")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = f"SELECT title, price, condition, seller_name FROM listings WHERE id IN ({','.join(['?'] * len(selected_ids))})"
    c.execute(query, selected_ids)
    entries = c.fetchall()
    conn.close()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, "eBay Listings Export", ln=True, align="C")

    for entry in entries:
        pdf.cell(0, 10, f"Title: {entry[0]}", ln=True)
        pdf.cell(0, 10, f"Price: {entry[1]}", ln=True)
        pdf.cell(0, 10, f"Condition: {entry[2]}", ln=True)
        pdf.cell(0, 10, f"Seller: {entry[3]}", ln=True)
        pdf.ln(10)

    pdf_file = "ebay_export.pdf"
    pdf.output(pdf_file)

    return send_file(pdf_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
