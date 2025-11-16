# 🧪 Testing Report – MAFD MVP

## ✔ Unit Testing
- ML anomaly scoring tested  
- Ticket schema verification  
- API health tests  

---

## ✔ Scenario Testing
Tested scenarios:
1. Overload Trip  
2. Relay Miscoordination  
3. Theft Overload  

All triggered correct anomaly detection.

---

## ✔ Latency Benchmark
| Run | Latency (s) |
|-----|-------------|
| 1 | 4.83 |
| 2 | 5.12 |
| 3 | 4.77 |

All < 60 seconds.

---

## ✔ RAG Retrieval Quality
Every ticket included at least one valid SOP citation.

---

## ✔ UI Verification
Streamlit displayed:
- Real signal plot  
- Ticket  
- Reasoning trace  
- SOP citations  
