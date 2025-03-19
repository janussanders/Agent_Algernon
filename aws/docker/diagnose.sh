#!/bin/bash

echo "=== Environment Variables ==="
echo "QDRANT_HOST: $QDRANT_HOST"
echo "QDRANT_PORT: $QDRANT_PORT"
echo "QDRANT_HTTPS: $QDRANT_HTTPS"
echo "STREAMLIT_SERVER_PORT: $STREAMLIT_SERVER_PORT"
echo "STREAMLIT_SERVER_WEBSOCKET_PORT: $STREAMLIT_SERVER_WEBSOCKET_PORT"

echo -e "\n=== Process Information ==="
echo "Checking running processes..."
ps aux | grep -E "streamlit|python|qdrant"
echo "Checking listening ports..."
netstat -tulpn
echo "Checking established connections..."
netstat -an | grep ESTABLISHED

echo -e "\n=== Network Information ==="
echo "Network interfaces:"
ip addr
echo "Routing table:"
ip route
echo "DNS configuration:"
cat /etc/resolv.conf

echo -e "\n=== WebSocket Tests ==="
echo "Testing WebSocket connectivity (port 8501)..."
curl -v -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Host: localhost:8501" \
     -H "Origin: http://localhost:8501" \
     "http://localhost:8501/stream" 2>&1 | grep "< HTTP"

echo -e "\n=== Qdrant Connection Tests ==="
echo "Testing TCP connection to Qdrant..."
for i in {1..3}; do
    echo "Attempt $i:"
    timeout 5 nc -zv $QDRANT_HOST $QDRANT_PORT 2>&1
    echo "Exit code: $?"
done

echo "Testing HTTP connection to Qdrant..."
curl -v --max-time 5 "http://$QDRANT_HOST:$QDRANT_PORT/healthz" 2>&1

echo -e "\n=== Network Path Analysis ==="
echo "Tracing route to Qdrant host..."
traceroute $QDRANT_HOST
echo "Checking network connectivity..."
mtr -n -c 1 $QDRANT_HOST || true

echo -e "\n=== Security Group Tests ==="
echo "Testing outbound connectivity..."
curl -v --max-time 5 https://api.ipify.org || true
echo "Testing internal VPC connectivity..."
ping -c 3 $QDRANT_HOST || true

echo -e "\n=== VPC Information ==="
echo "VPC Metadata:"
curl -s http://169.254.169.254/latest/meta-data/vpc-id
echo "Network interfaces:"
curl -s http://169.254.169.254/latest/meta-data/network/interfaces/macs/

echo -e "\n=== Streamlit Debug Information ==="
echo "Checking Streamlit configuration..."
python3 -c "import streamlit as st; print(st.config.get_option('server'))" || true
echo "Checking WebSocket server status..."
curl -v -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Host: localhost:8501" \
     -H "Origin: http://localhost:8501" \
     "http://localhost:8501/_stcore/health" 2>&1 | grep "< HTTP" 