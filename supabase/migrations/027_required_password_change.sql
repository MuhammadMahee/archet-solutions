-- Schema only: enforcement is an explicit one-time operation after deployment.
ALTER TABLE public.portal_users
    ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;
