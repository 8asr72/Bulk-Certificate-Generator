# Bulk-Certificate-Generator
This solution uses FastAPI and Celery to process bulk certificate generation asynchronously. It isolates failures, ensuring one bad record won't unnecessarily prevent the rest of the valid certificates from generating. Clients can track live progress and retrieve completed certificates in bulk.
