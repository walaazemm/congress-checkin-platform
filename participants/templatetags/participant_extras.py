from django import template

register = template.Library()

@register.filter
def get_meal_field(participant, field_name):
    """Get meal field value dynamically (e.g., 'breakfast_day1')"""
    return getattr(participant, field_name, False)