FROM restaurant-pos-backend:uat-password-policy-20261020-r2
COPY backend/app/services/uat_owner_identity.py /app/app/services/uat_owner_identity.py
COPY backend/app/services/platform_service.py /app/app/services/platform_service.py
COPY backend/app/services/saas_membership_service.py /app/app/services/saas_membership_service.py
COPY backend/app/dependencies.py /app/app/dependencies.py
COPY backend/app/services/company_access_service.py /app/app/services/company_access_service.py
COPY backend/tests/test_uat_owner_identity.py /opt/owner-tests/test_uat_owner_identity.py
