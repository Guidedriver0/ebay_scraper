# Use official Python image
FROM python:3.9

# Set the working directory inside the container
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dependencies for Chrome & Chromedriver
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    chromium \
    chromium-driver

# Copy all application files
COPY . .

# Set environment variables for Chrome and Chromedriver inside Docker
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV GOOGLE_CHROME_BIN=/usr/bin/chromium

# Expose port 5000 for Flask app
EXPOSE 5000

# Start Flask app
CMD ["python", "app.py"]
