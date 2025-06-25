"""

# OnlyIfYouKnow API Documentation

## Base URL: /api/

## Authentication

All endpoints require JWT authentication except:

- POST /api/auth/users/ (registration)
- POST /api/auth/jwt/create/ (login)
- GET /api/health/ (health check)

## Endpoints

### Authentication

- POST /api/auth/users/ - Register new user
- POST /api/auth/jwt/create/ - Login and get JWT tokens
- POST /api/auth/jwt/refresh/ - Refresh access token

### Users

- GET /api/users/ - List users (filtered by user type)
- POST /api/users/register/ - Register with invitation token
- GET /api/users/profile/ - Get current user profile
- PATCH /api/users/update_profile/ - Update profile

### Properties

- GET /api/properties/ - List properties (filtered by access)
- POST /api/properties/ - Create property (owners only)
- GET /api/properties/{id}/ - Get property details
- PUT/PATCH /api/properties/{id}/ - Update property
- POST /api/properties/{id}/submit_for_approval/ - Submit for approval
- POST /api/properties/{id}/approve/ - Approve property (admin)
- POST /api/properties/{id}/enlist_to_beds24/ - Enlist to Beds24 (admin)

### Bookings

- GET /api/bookings/ - List bookings
- POST /api/bookings/ - Create booking
- GET /api/bookings/{id}/ - Get booking details
- PATCH /api/bookings/{id}/update_status/ - Update booking status

### Invitations

- GET /api/invitations/ - List invitations
- POST /api/invitations/ - Create invitation (admin)
- POST /api/invitations/validate_token/ - Validate onboarding token
- POST /api/invitations/respond_to_invitation/ - Accept/reject invitation

### Trust Network

- GET /api/network-invitations/ - List network invitations (owner)
- POST /api/network-invitations/ - Create network invitation (owner)
- POST /api/network-invitations/respond_to_network_invitation/ - Respond to invitation
- GET /api/trusted-networks/ - List trusted users (owner)
- PATCH /api/trusted-networks/{id}/update_trust_level/ - Update trust level
- DELETE /api/trusted-networks/{id}/remove_from_network/ - Remove from network

### Trust Levels

- GET /api/trust-levels/ - List trust level definitions (owner)
- POST /api/trust-levels/ - Create trust level definition
- PUT/PATCH /api/trust-levels/{id}/ - Update trust level definition

### Analytics

- GET /api/analytics/dashboard_metrics/ - Get dashboard metrics
- GET /api/analytics/recent_activity/ - Get recent activity logs

## Query Parameters

Most list endpoints support:

- page: Page number
- page_size: Items per page (max 100)
- search: Search term
- ordering: Field to order by (prefix with - for descending)

## Response Format

All responses follow this format:

```json
{
  "count": 100,
  "next": "http://api.example.org/accounts/?page=4",
  "previous": "http://api.example.org/accounts/?page=2",
  "results": [...]
}
```

## Error Responses

```json
{
  "error": "Error message",
  "details": "Detailed error information"
}
```

## Rate Limiting

- Anonymous users: 100 requests/hour
- Regular users: 1000 requests/hour
- Owners: 2000 requests/hour
- Admins: 5000 requests/hour
  """
  """
  iCal API Endpoints (READY TO USE):

1. Export Property Calendar:
   GET /api/properties/{id}/ical_export/?start=2025-01-01&end=2025-12-31
2. Setup iCal Sync:
   POST /api/properties/{id}/setup_ical_sync/
   {
   "import_enabled": true,
   "export_enabled": true,
   "auto_block": true,
   "sync_interval": 24,
   "timezone": "UTC"
   }
3. Add External Calendar:
   POST /api/properties/{id}/add_external_calendar/
   {
   "calendar_url": "https://airbnb.com/calendar/ical/...",
   "calendar_name": "Airbnb Calendar"
   }
4. Manual Sync Trigger:
   POST /api/properties/{id}/sync_ical/
5. Get Property with iCal Data:
   GET /api/properties/{id}/
   # Returns property with ical_import_url, ical_export_url, etc.
   """
