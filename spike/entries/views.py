from functools import wraps

from django.contrib.auth.views import LoginView, LogoutView, redirect_to_login
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .forms import EntryForm, KitAuthenticationForm
from .models import Entry

RECENT_LIMIT = 10


def kit_login_required(view):
    """Like login_required, but sends people to the login page of the same kit."""

    @wraps(view)
    def wrapper(request, kit, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=f"/{kit}/login/")
        return view(request, kit, *args, **kwargs)

    return wrapper


def recent_entries():
    return Entry.objects.select_related("recorded_by")[:RECENT_LIMIT]


def render_entry_screen(request, kit, form, saved=False):
    """Full page for normal requests, just the panel for HTMX requests."""
    template = "_panel.html" if request.headers.get("HX-Request") else "page.html"
    context = {"kit": kit, "form": form, "entries": recent_entries(), "saved": saved}
    return render(request, f"entries/{kit}/{template}", context)


@require_GET
def home(request):
    return render(request, "entries/home.html")


@require_GET
@kit_login_required
def entry_page(request, kit):
    return render_entry_screen(request, kit, EntryForm())


@require_POST
@kit_login_required
def create_entry(request, kit):
    form = EntryForm(request.POST)
    if not form.is_valid():
        return render_entry_screen(request, kit, form)

    entry = form.save(commit=False)
    entry.recorded_by = request.user
    entry.save()
    return render_entry_screen(request, kit, EntryForm(), saved=True)


def kit_login(request, kit):
    view = LoginView.as_view(
        template_name=f"entries/{kit}/login.html",
        authentication_form=KitAuthenticationForm,
        next_page=f"/{kit}/",
        extra_context={"kit": kit},
    )
    return view(request)


def kit_logout(request, kit):
    return LogoutView.as_view(next_page=f"/{kit}/login/")(request)
