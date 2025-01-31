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
            shipping_location TEXT,
            shipping_cost TEXT,
            return_policy TEXT,
            description TEXT,
            image_urls TEXT,
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
    """Scrapes an eBay listing for all key details, including images and location."""
    driver = get_webdriver()
    driver.get(url)
    time.sleep(3)  # Allow JavaScript to load

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    # Extract title
    try:
        title = soup.find("h1", {"class": "x-item-title__mainTitle"}).text.strip()
    except AttributeError:
        title = "Not Found"

    # Extract price
    try:
        price = soup.find("span", {"itemprop": "price"}).text.strip()
    except AttributeError:
        price = "Not Found"

    # Extract condition
    try:
        condition = soup.find("div", {"class": "x-item-condition-text"}).text.strip()
    except AttributeError:
        condition = "Not Found"

    # Extract seller name
    try:
        seller_name = soup.find("span", {"class": "ux-textspans ux-textspans--BOLD"}).text.strip()
    except AttributeError:
        seller_name = "Not Found"

    # Extract seller feedback score
    try:
        feedback_score = soup.find("span", {"class": "ux-textspans"}).text.strip()
    except AttributeError:
        feedback_score = "Not Found"

    # Extract shipping location
    try:
        shipping_location = soup.find("div", {"class": "ux-labels-values__values"}).text.strip()
    except AttributeError:
        shipping_location = "Not Found"

    # Extract shipping cost
    try:
        shipping_cost = soup.find("span", {"id": "fshippingCost"}).text.strip()
    except AttributeError:
        shipping_cost = "Not Found"

    # Extract return policy
    try:
        return_policy = soup.find("div", {"class": "ux-labels-values__values"}).text.strip()
    except AttributeError:
        return_policy = "Not Found"

    # Extract full item description
    try:
        description_tag = soup.find("div", {"id": "desc_ifr"})
        if description_tag:
            description = description_tag.text.strip()
        else:
            description = "Not Found"
    except AttributeError:
        description = "Not Found"

    # Extract all images
    image_urls = []
    try:
        img_tags = soup.select("img[src*='.jpg']")
        for img in img_tags:
            img_url = img["src"]
            if "ebayimg.com" in img_url:
                image_urls.append(img_url)
    except:
        image_urls = []

    return {
        "title": title,
        "price": price,
        "condition": condition,
        "seller_name": seller_name,
        "seller_feedback_score": feedback_score,
        "shipping_location": shipping_location,
        "shipping_cost": shipping_cost,
        "return_policy": return_policy,
        "description": description,
        "image_urls": "; ".join(image_urls),
        "listing_url": url
    }

def save_to_db(data):
    """Inserts scraped listing into the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO listings (title, price, condition, seller_name, seller_feedback_score, 
                              shipping_location, shipping_cost, return_policy, description, 
                              image_urls, listing_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data["title"], data["price"], data["condition"], data["seller_name"], 
          data["seller_feedback_score"], data["shipping_location"], data["shipping_cost"],
          data["return_policy"], data["description"], data["image_urls"], data["listing_url"]))
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
@app.route("/export_pdf", methods=["POST"])
def export_pdf():
    """Exports selected entries as a formatted PDF with a table."""
    selected_ids = request.form.getlist("selected_ids")
    selected_fields = request.form.getlist("selected_fields")

    if not selected_ids:
        return jsonify({"status": "error", "message": "No entries selected"}), 400

    if not selected_fields:
        return jsonify({"status": "error", "message": "No fields selected"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Dynamically generate the SQL query based on selected fields
    query_fields = ", ".join(selected_fields)
    query = f"SELECT {query_fields} FROM listings WHERE id IN ({','.join(['?'] * len(selected_ids))})"
    c.execute(query, selected_ids)
    entries = c.fetchall()
    conn.close()

    # Create PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, "eBay Listings Export", ln=True, align="C")
    pdf.ln(10)

    column_widths = [50, 40, 50, 50]
    headers = selected_fields  # Dynamic headers based on user selection

    # Draw table headers
    for i, header in enumerate(headers):
        pdf.cell(column_widths[i % len(column_widths)], 10, header.replace("_", " ").title(), 1, 0, "C")
    pdf.ln()

    # Draw table content
    for entry in entries:
        for i, field in enumerate(entry):
            pdf.cell(column_widths[i % len(column_widths)], 10, str(field), 1, 0, "C")
        pdf.ln()

    pdf_file = "ebay_export.pdf"
    pdf.output(pdf_file)

    return send_file(pdf_file, as_attachment=True)


@app.route("/delete_selected", methods=["POST"])
def delete_selected():
    """Deletes multiple selected entries from the database."""
    selected_ids = request.json.get("selected_ids", [])
    
    if not selected_ids:
        return jsonify({"status": "error", "message": "No entries selected"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = f"DELETE FROM listings WHERE id IN ({','.join(['?'] * len(selected_ids))})"
    c.execute(query, selected_ids)
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "Selected listings deleted"}), 200

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
