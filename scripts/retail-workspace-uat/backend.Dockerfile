# Historical UAT.11 overlay: build ONLY with the captured live-backend sources
# from the verified release artifact. Repository HEAD has a different (gated
# Stripe) baseline; copying root checkout files here is not a production build.
FROM restaurant-pos-backend:uat-retail-images-20261025-r1
COPY backend/app/routers/pos.py /app/app/routers/pos.py
COPY backend/app/schemas/pos.py /app/app/schemas/pos.py
COPY backend/app/services/sale_service.py /app/app/services/sale_service.py
