# Include inside a location / { } in extra HTTP servers when WG_MFA=true.
# Requires the MFA locations from healthz-mfa.conf.template (same server or copy).
auth_request /mfa/auth;
error_page 401 = @mfa_login;
