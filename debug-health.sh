#!/bin/bash

set -e

echo "🔍 Debugging health check issues..."

# Docker compose command
DC_CMD="docker compose --env-file .env.production -f docker-compose.production.yml"

echo "📊 Current container status:"
$DC_CMD ps

echo ""
echo "🌐 Testing connectivity at different levels:"

# Test 1: Direct container connectivity
echo "1. Testing direct web container health:"
if $DC_CMD exec -T web curl -f http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "   ✅ Web container internal health check: PASS"
else
    echo "   ❌ Web container internal health check: FAIL"
    echo "   📋 Web container logs:"
    $DC_CMD logs --tail=20 web
fi

# Test 2: Host to web container (if port is exposed)
echo "2. Testing host to web container (port 8000):"
if curl -f -m 5 http://localhost:8000/api/health/ > /dev/null 2>&1; then
    echo "   ✅ Host to web container: PASS"
else
    echo "   ❌ Host to web container: FAIL"
fi

# Test 3: Host to nginx (port 80)
echo "3. Testing host to nginx (port 80):"
if curl -f -m 5 http://localhost/api/health/ > /dev/null 2>&1; then
    echo "   ✅ Host to nginx: PASS"
else
    echo "   ❌ Host to nginx: FAIL"
    echo "   📋 Nginx container logs:"
    $DC_CMD logs --tail=20 nginx
fi

# Test 4: Nginx to web container connectivity
echo "4. Testing nginx to web container connectivity:"
if $DC_CMD exec -T nginx curl -f http://web:8000/api/health/ > /dev/null 2>&1; then
    echo "   ✅ Nginx to web container: PASS"
else
    echo "   ❌ Nginx to web container: FAIL"
    echo "   📋 Network info:"
    $DC_CMD exec -T nginx nslookup web || echo "   DNS resolution for 'web' failed"
fi

# Test 5: Check port bindings
echo "5. Checking port bindings:"
echo "   Nginx ports:"
docker port $(docker ps -q -f name=oifyk_nginx) 2>/dev/null || echo "   No nginx container found"
echo "   Web ports:"
docker port $(docker ps -q -f name=oifyk_web) 2>/dev/null || echo "   No web container found"

# Test 6: Check nginx configuration
echo "6. Testing nginx configuration:"
if $DC_CMD exec -T nginx nginx -t > /dev/null 2>&1; then
    echo "   ✅ Nginx configuration: VALID"
else
    echo "   ❌ Nginx configuration: INVALID"
    echo "   📋 Nginx config test output:"
    $DC_CMD exec -T nginx nginx -t
fi

# Test 7: Check health endpoint directly
echo "7. Testing health endpoint response:"
echo "   Direct response from web container:"
$DC_CMD exec -T web curl -s http://localhost:8000/api/health/ | head -c 200 || echo "   No response"

# Test 8: Check if processes are running
echo "8. Checking running processes:"
echo "   Gunicorn processes in web container:"
$DC_CMD exec -T web ps aux | grep gunicorn || echo "   No gunicorn processes found"
echo "   Nginx processes in nginx container:"
$DC_CMD exec -T nginx ps aux | grep nginx || echo "   No nginx processes found"

# Test 9: Check network connectivity
echo "9. Network connectivity test:"
echo "   Ping from nginx to web:"
$DC_CMD exec -T nginx ping -c 1 web > /dev/null 2>&1 && echo "   ✅ Can ping web" || echo "   ❌ Cannot ping web"

# Test 10: Check firewall/iptables
echo "10. System-level connectivity:"
echo "    Checking if ports are listening:"
netstat -tlnp 2>/dev/null | grep -E ':(80|8000)\s' || echo "    No web ports listening on host"

echo ""
echo "🔧 Quick fixes to try:"
echo "1. Restart nginx: $DC_CMD restart nginx"
echo "2. Restart web: $DC_CMD restart web"
echo "3. Check logs: $DC_CMD logs -f nginx web"
echo "4. Full restart: $DC_CMD down && $DC_CMD up -d"