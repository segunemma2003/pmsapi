from icalendar import Calendar, Event, vDatetime
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
import pytz
import requests
import uuid

class ICalService:
    """Enhanced iCal service for calendar management"""
    
    @staticmethod
    def generate_property_calendar(property_obj, start_date, end_date):
        """Generate comprehensive iCal calendar for property bookings"""
        cal = Calendar()
        cal.add('prodid', f'-//OnlyIfYouKnow//Property {property_obj.id}//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', f'{property_obj.title} - Bookings')
        cal.add('x-wr-caldesc', f'Booking calendar for {property_obj.title}')
        cal.add('x-wr-timezone', property_obj.ical_timezone or 'UTC')
        cal.add('x-wr-relcalid', str(property_obj.id))
        
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
            event.add('created', booking.created_at)
            event.add('last-modified', booking.updated_at)
            
            # Enhanced summary with status
            status_emoji = '✅' if booking.status == 'confirmed' else '⏳'
            event.add('summary', f'{status_emoji} {booking.guest.full_name} - {booking.guests_count} guests')
            
            # Detailed description
            description = f'''
PROPERTY: {property_obj.title}
GUEST: {booking.guest.full_name}
EMAIL: {booking.guest.email}
GUESTS: {booking.guests_count}
TOTAL: ${booking.total_amount}
STATUS: {booking.status.title()}
CHECK-IN: {booking.check_in_date}
CHECK-OUT: {booking.check_out_date}
SPECIAL REQUESTS: {booking.special_requests or 'None'}
BOOKING ID: {booking.id}
            '''.strip()
            event.add('description', description)
            
            event.add('location', f'{property_obj.address}, {property_obj.city}')
            event.add('status', 'CONFIRMED' if booking.status == 'confirmed' else 'TENTATIVE')
            event.add('transp', 'OPAQUE')  # Show as busy
            
            # Add categories
            event.add('categories', ['BOOKING', booking.status.upper()])
            
            # Add custom properties
            event.add('x-booking-id', str(booking.id))
            event.add('x-guest-count', str(booking.guests_count))
            event.add('x-total-amount', str(booking.total_amount))
            
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
                    # Extract dates
                    start_dt = component.get('dtstart')
                    end_dt = component.get('dtend')
                    
                    if start_dt and end_dt:
                        start_date = start_dt.dt
                        end_date = end_dt.dt
                        
                        # Handle datetime vs date objects
                        if hasattr(start_date, 'date'):
                            start_date = start_date.date()
                        if hasattr(end_date, 'date'):
                            end_date = end_date.date()
                        
                        booking_data = {
                            'start_date': start_date,
                            'end_date': end_date,
                            'summary': str(component.get('summary', '')),
                            'description': str(component.get('description', '')),
                            'uid': str(component.get('uid', '')),
                            'status': str(component.get('status', 'CONFIRMED')),
                            'created': component.get('dtstamp').dt if component.get('dtstamp') else None,
                            'location': str(component.get('location', '')),
                            'categories': str(component.get('categories', ''))
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
    def fetch_external_calendar(calendar_url, timeout=30):
        """Fetch external iCal calendar with proper headers"""
        try:
            headers = {
                'User-Agent': 'OnlyIfYouKnow/1.0 (Calendar Sync)',
                'Accept': 'text/calendar, application/calendar, text/plain',
                'Cache-Control': 'no-cache'
            }
            
            response = requests.get(calendar_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            return {
                'success': True,
                'ical_data': response.text,
                'content_type': response.headers.get('content-type', ''),
                'last_modified': response.headers.get('last-modified', ''),
                'etag': response.headers.get('etag', '')
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to fetch calendar: {str(e)}"
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
        cal.add('x-wr-caldesc', f'Blocked dates for {property_obj.title}')
        
        for blocked_date in blocked_dates:
            event = Event()
            event.add('uid', f'blocked-{blocked_date["id"]}@oifyk.com')
            event.add('dtstart', blocked_date['date'])
            event.add('dtend', blocked_date['date'] + timedelta(days=1))
            event.add('summary', '🚫 Not Available')
            event.add('description', blocked_date.get('reason', 'Date blocked by owner'))
            event.add('status', 'CONFIRMED')
            event.add('transp', 'OPAQUE')  # Show as busy
            event.add('categories', ['BLOCKED'])
            
            cal.add_component(event)
        
        return cal.to_ical().decode('utf-8')
    
    @staticmethod
    def validate_ical_url(url):
        """Validate if URL returns valid iCal data"""
        try:
            result = ICalService.fetch_external_calendar(url, timeout=10)
            if not result['success']:
                return {'valid': False, 'error': result['error']}
            
            parse_result = ICalService.parse_external_calendar(result['ical_data'])
            if not parse_result['success']:
                return {'valid': False, 'error': parse_result['error']}
            
            return {
                'valid': True, 
                'events_found': parse_result['count'],
                'content_type': result['content_type']
            }
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}
