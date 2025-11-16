# 📘 API Reference – Multi-Agent Fault Detection (MAFD)

## Overview
This document provides a complete reference for all FastAPI endpoints used in the MVP.

---

## **GET /health**
Health check endpoint.

**Response**
```json
{"status": "ok"}
```

---

## **POST /detect**
Runs the baseline anomaly detector.

**Request**
```json
{"scenario": "overload_trip", "bus_id": "bus_1"}
```

**Response**
Detection summary containing anomaly metrics and evidence windows.

---

## **POST /ticket**
Converts detection output into a structured Fault Ticket.

**Response Fields**
- faultType  
- summary  
- root_cause  
- kb_citations  
- evidence  

---

## **GET /tickets**
Returns all stored tickets.

---

## **GET /signals**
Returns CSV-based signal data for Streamlit visualization.
