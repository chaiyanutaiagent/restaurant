FROM restaurant-pos-backend:uat-sketchbiz-host-20261016-r1
USER root
# Preserve server-only role schema additions; narrowly alter three customer fields.
RUN python -c 'from pathlib import Path; old="Field(min_length=12, max_length=128)"; new="Field(min_length=8, max_length=128)"; targets=[(Path("/app/app/schemas/membership.py"),2),(Path("/app/app/schemas/platform.py"),1)]; contents=[(p,p.read_text(),n) for p,n in targets]; assert all(s.count(old)==n for p,s,n in contents), "Unexpected password schema baseline"; [(p.write_text(s.replace(old,new))) for p,s,n in contents]'
USER app
