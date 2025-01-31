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

CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"  # Update with your path

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920x1080")

DB_FILE = "ebay_listings.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            seller_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_ebay_listing(url):
    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get(url)
    time.sleep(3)
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    try:
        title = soup.find("h1").text.strip()
    except AttributeError:
        title = "Not Found"

    try:
        price = soup.find("span", {"itemprop": "price"}).text.strip()
    except AttributeError:
        price = "Not Found"

    try:
        seller_name = soup.find("span", {"class": "ux-textspans ux-textspans--BOLD"}).text.strip()
    except AttributeError:
        seller_name = "Not Found"

    return {"title": title, "price": price, "seller_name": seller_name, "listing_url": url}

def save_to_db(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO listings (title, price, seller_name) VALUES (?, ?, ?)", 
              (data["title"], data["price"], data["seller_name"]))
    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def index():
    listing_data = None
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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM listings")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route("/export_pdf", methods=["POST"])
def export_pdf():
    selected_ids = request.form.getlist("selected_ids")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = f"SELECT title, price, seller_name FROM listings WHERE id IN ({','.join(['?'] * len(selected_ids))})"
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
        pdf.cell(0, 10, f"Seller: {entry[2]}", ln=True)
        pdf.ln(10)

    pdf_file = "ebay_export.pdf"
    pdf.output(pdf_file)

    return send_file(pdf_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
