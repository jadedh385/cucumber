import datetime

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .models import Entry

MAX_DAYS_BACK = 7

# daisyUI and Basecoat both style these class names, so one form serves both kits.
INPUT_CLASS = "input w-full"
SELECT_CLASS = "select w-full"
TEXTAREA_CLASS = "textarea w-full"


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ["batch_code", "action", "quantity", "occurred_on", "note"]
        widgets = {
            "batch_code": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "BAT-00012", "autocapitalize": "characters"}
            ),
            "action": forms.Select(attrs={"class": SELECT_CLASS}),
            "quantity": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "inputmode": "numeric", "min": "1"}
            ),
            "occurred_on": forms.DateInput(
                attrs={"class": INPUT_CLASS, "type": "date"}, format="%Y-%m-%d"
            ),
            "note": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 2}),
        }

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity < 1:
            raise forms.ValidationError("Quantity must be at least 1.")
        return quantity

    def clean_occurred_on(self):
        occurred_on = self.cleaned_data["occurred_on"]
        today = timezone.localdate()
        if occurred_on > today:
            raise forms.ValidationError("The date can't be in the future.")
        if occurred_on < today - datetime.timedelta(days=MAX_DAYS_BACK):
            raise forms.ValidationError(
                f"You can pick a date up to {MAX_DAYS_BACK} days back. "
                "For older work, log it today with the real date in the note."
            )
        return occurred_on


class KitAuthenticationForm(AuthenticationForm):
    """Django's login form with the shared input class on its fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
