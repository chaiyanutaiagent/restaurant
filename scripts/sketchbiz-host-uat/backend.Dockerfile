FROM restaurant-pos-backend:uat-retail-catalog-20261014-r2
COPY backend/app/main.py /app/app/main.py
COPY backend/app/middleware/tenant_host.py /app/app/middleware/tenant_host.py
