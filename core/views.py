from django.shortcuts import render


def pricing_sandbox(request):
    """Simple internal test UI: input code and contract ID, see JSON pricing response."""
    return render(request, "pricing_sandbox.html")
