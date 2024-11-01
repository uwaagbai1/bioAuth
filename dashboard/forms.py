# forms.py
from django import forms
from accounts.models import Profile
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'profile_picture', 'job', 'about_me']

    def __init__(self, *args, **kwargs):
        super(ProfileUpdateForm, self).__init__(*args, **kwargs)

        # Update widget attributes for each field
        self.fields['first_name'].widget.attrs.update({
            'class': 'input',
            'required': True
        })
        self.fields['last_name'].widget.attrs.update({
            'class': 'input',
            'required': True
        })
        self.fields['profile_picture'].widget.attrs.update({
            'accept': '.png, .jpg, .jpeg',
            'type': 'file'
        })
        self.fields['job'].widget.attrs.update({
            'class': 'input',
            'required': True
        })
        self.fields['about_me'].widget.attrs.update({
            'class': 'input',
            'required': True
        })

        # Set up Crispy Forms helper for profile picture only
        self.helper = FormHelper()
        self.helper.form_tag = False  # Prevent Crispy from adding <form> tags
        self.helper.layout = Layout(
            Field('profile_picture', css_class='form-control-file')
        )
