-- Run as schema owner after every migration. No ownership is granted to the runtime.
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_roles WHERE rolname = 'docqa_app'
        AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) OR EXISTS (
        SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'docqa_app'
    ) OR EXISTS (
        SELECT FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
        WHERE r.rolname = 'docqa_app'
    ) OR EXISTS (
        SELECT FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
        WHERE r.rolname = 'docqa_app'
    ) OR EXISTS (
        SELECT FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba
        WHERE r.rolname = 'docqa_app'
    ) THEN
        RAISE EXCEPTION 'docqa_app already has ownership or elevated privileges; operator review required';
    END IF;
END $$;
REVOKE ALL ON DATABASE docqa FROM PUBLIC;
REVOKE ALL ON DATABASE docqa FROM docqa_app;
GRANT CONNECT ON DATABASE docqa TO docqa_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM docqa_app;
GRANT USAGE ON SCHEMA public TO docqa_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM docqa_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO docqa_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM docqa_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO docqa_app;
ALTER DEFAULT PRIVILEGES FOR ROLE docqa IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO docqa_app;
ALTER DEFAULT PRIVILEGES FOR ROLE docqa IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO docqa_app;
REVOKE ALL ON TABLE alembic_version FROM docqa_app;
