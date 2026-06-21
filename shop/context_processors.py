# context_processors.py
from products.models import Category

def global_footer_categories(request):
    """
    Injects specific categories into every single template context 
    automatically so that global footer links never break.
    """
    return {
        "private_reserve": Category.objects.filter(name__iexact="Private reserve").first(),
        "limited_edition": Category.objects.filter(name__iexact="Limited edition").first(),
    }