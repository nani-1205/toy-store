from datetime import datetime
import pytz
import locale

# Set locale for currency formatting (may need OS-level setup for 'en_IN')
# Try common fallbacks if 'en_IN' is not available
locales_to_try = ['en_IN', 'en_IN.utf8', 'en_IN.UTF-8', 'en_US', 'en_US.utf8', 'en_US.UTF-8', 'C.UTF-8', 'C']
found_locale = False
for loc in locales_to_try:
    try:
        locale.setlocale(locale.LC_MONETARY, loc)
        found_locale = True
        print(f"Using locale: {loc}")
        break
    except locale.Error:
        continue

if not found_locale:
    print("Warning: Could not set locale for INR formatting. Using basic fallback.")

IST = pytz.timezone('Asia/Kolkata')

def format_inr(value):
    """Formats a number as Indian Rupees (₹)."""
    try:
        # Use locale-based formatting if available
        return locale.currency(float(value), symbol='₹', grouping=True)
    except (ValueError, TypeError):
         # Fallback formatting
        try:
            return f"₹{float(value):,.2f}"
        except (ValueError, TypeError):
            return "₹ - Invalid Amount -"


def format_datetime_ist(dt):
    """Formats a datetime object to a readable IST string."""
    if not dt:
        return "N/A"
    if dt.tzinfo is None:
        # Assume UTC if no timezone, then convert to IST
        dt = pytz.utc.localize(dt).astimezone(IST)
    else:
        # Convert to IST if it's not already
        dt = dt.astimezone(IST)
    return dt.strftime('%d %b %Y, %I:%M %p %Z') # Example: 25 Dec 2023, 02:30 PM IST