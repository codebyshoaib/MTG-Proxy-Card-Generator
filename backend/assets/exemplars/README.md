# Exemplar reference cards for conditioning Creative Full.
#
# These are the client's third-party proxy crops (see generation/exemplars.py). They are
# tracked in this *private* deploy repo so Render's Docker build has them on disk — a clean
# public handover must not include them; Milestone 2 replaces them with an owned set.
#
# Local clones that still exclude this tree via .git/info/exclude can rebuild with:
#   uv run python manage.py prepare_exemplars '../../Project Material/CLIENT-FAVORITES-2026-08-19'
