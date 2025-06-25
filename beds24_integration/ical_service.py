from icalendar import Calendar, Event, vDatetime
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
import pytz

class ICalService:
    """Service for generating and parsing iCal data"""
    
    @staticmethod
    def generate_property_calendar(property_obj, start_date, end_date):
        """Generate iCal calendar for a property's bookings"""
        cal = Calendar()
        cal.add('prodid', f'-//OnlyIfYouKnow//Property {property_obj.id}//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', f'{property_obj.title} - Bookings')
        cal.add('x-wr-caldesc', f'Booking calendar for {property_obj.title}')
        cal.add('x-wr-timezone', property_obj.ical_timezone or 'UTC')
        
        # Get bookings in date range
        bookings = property_obj.bookings.filter(
            check_in_date__lte=end_date,
            check_out_date__gte=start_date,
            status__in=['confirmed', 'pending']
        ).select_related('guest')
        
        for booking in bookings:
            event = Event()
            event.add('uid', f'booking-{booking.id}@oifyk.com')
            event.add('dtstart', booking.check_in_date)
            event.add('dtend', booking.check_out_date)
            event.add('dtstamp', booking.created_at)
            event.add('summary', f'Booking - {booking.guest.full_name}')
            event.add('description', f'''
Property: {property_obj.title}
Guest: {booking.guest.full_name}
Guests: {booking.guests_count}
Total: ${booking.total_amount}
Status: {booking.status.title()}
Special Requests: {booking.special_requests or 'None'}
            '''.strip())
            event.add('location', f'{property_obj.address}, {property_obj.city}')
            event.add('status', 'CONFIRMED' if booking.status == 'confirmed' else 'TENTATIVE')
            
            cal.add_component(event)
        
        return cal.to_ical().decode('utf-8')
    
    @staticmethod
    def parse_external_calendar(ical_data):
        """Parse external iCal data and extract booking information"""
        try:
            cal = Calendar.from_ical(ical_data)
            bookings = []
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    booking_data = {
                        'start_date': component.get('dtstart').dt,
                        'end_date': component.get('dtend').dt,
                        'summary': str(component.get('summary', '')),
                        'description': str(component.get('description', '')),
                        'uid': str(component.get('uid', '')),
                        'status': str(component.get('status', 'CONFIRMED')),
                        'created': component.get('dtstamp').dt if component.get('dtstamp') else None
                    }
                    bookings.append(booking_data)
            
            return {
                'success': True,
                'bookings': bookings,
                'count': len(bookings)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to parse iCal data: {str(e)}"
            }
    
    @staticmethod
    def create_blocked_dates_calendar(property_obj, blocked_dates):
        """Create iCal calendar for blocked dates"""
        cal = Calendar()
        cal.add('prodid', f'-//OnlyIfYouKnow//Property {property_obj.id} Blocked//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', f'{property_obj.title} - Blocked Dates')
        
        for blocked_date in blocked_dates:
            event = Event()
            event.add('uid', f'blocked-{blocked_date["id"]}@oifyk.com')
            event.add('dtstart', blocked_date['date'])
            event.add('dtend', blocked_date['date'] + timedelta(days=1))
            event.add('summary', 'Blocked - Not Available')
            event.add('description', blocked_date.get('reason', 'Date blocked by owner'))
            event.add('status', 'CONFIRMED')
            event.add('transp', 'OPAQUE')  # Show as busy
            
            cal.add_component(event)
        
        return cal.to_ical().decode('utf-8')