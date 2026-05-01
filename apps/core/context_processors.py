from django.conf import settings


def project_meta(request):
    return {
        "PROJECT_NAME": "Zeekr",
        "SUPPORTED_LANGUAGES": settings.LANGUAGES,
    }

