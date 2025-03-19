# Monitoring Guide

## Overview

This guide covers monitoring and observability for the RAG application, including application metrics, infrastructure monitoring, and logging.

## Application Monitoring

### 1. Health Checks

The application provides health check endpoints:

```bash
# Check application health
curl http://localhost:8501/health

# Check Qdrant health
curl http://localhost:6333/healthz
```

### 2. Application Metrics

Key metrics to monitor:

- Request latency
- Error rates
- Document processing time
- Query response time
- Memory usage
- CPU usage
- WebSocket connections

### 3. Logging

#### 3.1 Log Structure

```json
{
    "timestamp": "2024-03-19T12:00:00Z",
    "level": "INFO",
    "message": "Processing document",
    "module": "document_processor",
    "function": "process_document",
    "line": 123,
    "extra": {
        "document_id": "doc123",
        "file_name": "example.pdf",
        "file_size": 1024
    }
}
```

#### 3.2 Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: General operational information
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for actual issues
- **CRITICAL**: Critical issues requiring immediate attention

## Infrastructure Monitoring

### 1. AWS CloudWatch

#### 1.1 Metrics

- ECS Service Metrics:
  - CPU Utilization
  - Memory Usage
  - Running Tasks
  - Pending Tasks

- ECR Metrics:
  - Image Pull Count
  - Image Push Count
  - Repository Size

- Application Metrics:
  - Request Count
  - Error Rate
  - Latency
  - WebSocket Connections

#### 1.2 Alarms

Recommended CloudWatch alarms:

```yaml
# CPU Utilization Alarm
- Name: HighCPUUtilization
  Metric: CPUUtilization
  Threshold: 80
  Period: 300
  EvaluationPeriods: 2
  Statistic: Average

# Memory Usage Alarm
- Name: HighMemoryUsage
  Metric: MemoryUtilization
  Threshold: 85
  Period: 300
  EvaluationPeriods: 2
  Statistic: Average

# Error Rate Alarm
- Name: HighErrorRate
  Metric: ErrorRate
  Threshold: 5
  Period: 300
  EvaluationPeriods: 2
  Statistic: Sum
```

### 2. Container Monitoring

#### 2.1 Docker Metrics

```bash
# View container stats
docker stats

# View container logs
docker logs -f container_name

# View container events
docker events
```

#### 2.2 Resource Limits

Recommended container limits:

```yaml
# RAG App Container
resources:
  limits:
    cpu: 1024m
    memory: 2Gi
  requests:
    cpu: 512m
    memory: 1Gi

# Qdrant Container
resources:
  limits:
    cpu: 2048m
    memory: 4Gi
  requests:
    cpu: 1024m
    memory: 2Gi
```

## Performance Monitoring

### 1. Application Performance

#### 1.1 Key Metrics

- Document Processing:
  - Upload time
  - Processing time
  - Chunking time
  - Embedding time

- Query Performance:
  - Query latency
  - Vector search time
  - LLM processing time
  - Response streaming time

#### 1.2 Performance Thresholds

```yaml
# Document Processing
upload_time_threshold: 10s
processing_time_threshold: 30s
chunking_time_threshold: 5s
embedding_time_threshold: 15s

# Query Processing
query_latency_threshold: 2s
vector_search_threshold: 500ms
llm_processing_threshold: 1s
```

### 2. Resource Utilization

#### 2.1 Monitoring Points

- CPU Usage
- Memory Usage
- Disk I/O
- Network I/O
- WebSocket Connections

#### 2.2 Utilization Thresholds

```yaml
# Resource Thresholds
cpu_threshold: 80%
memory_threshold: 85%
disk_threshold: 90%
network_threshold: 70%
```

## Logging Best Practices

### 1. Structured Logging

```python
# Good logging example
logging.info("Processing document", extra={
    "document_id": doc_id,
    "file_name": file_name,
    "file_size": file_size,
    "processing_time": processing_time
})

# Bad logging example
logging.info(f"Processing document {doc_id}")
```

### 2. Log Levels

- **DEBUG**: Development and troubleshooting
- **INFO**: Normal operations
- **WARNING**: Potential issues
- **ERROR**: Actual issues
- **CRITICAL**: System failures

### 3. Log Rotation

```yaml
# Log Rotation Configuration
max_bytes: 10MB
backup_count: 5
```

## Monitoring Tools

### 1. CloudWatch Dashboard

Create a dashboard with the following widgets:

- ECS Service Metrics
- Application Metrics
- Error Rates
- Resource Utilization
- Log Streams

### 2. Alerting

Set up alerts for:

- High error rates
- Service health issues
- Resource utilization
- Performance degradation

### 3. Log Analysis

Use CloudWatch Logs Insights for:

- Error pattern analysis
- Performance analysis
- Usage patterns
- Security monitoring

## Troubleshooting

### 1. Common Issues

- High CPU Usage
- Memory Leaks
- Network Latency
- Service Unavailability
- Data Processing Errors

### 2. Investigation Steps

1. Check CloudWatch metrics
2. Review application logs
3. Check container health
4. Verify service status
5. Analyze error patterns

### 3. Resolution Process

1. Identify root cause
2. Implement fix
3. Monitor resolution
4. Document solution
5. Update monitoring

## Maintenance

### 1. Regular Tasks

- Review metrics
- Check logs
- Update dashboards
- Verify alerts
- Clean up old logs

### 2. Performance Tuning

- Monitor resource usage
- Optimize queries
- Adjust scaling
- Update configurations
- Review thresholds

### 3. Documentation

- Update monitoring guide
- Document incidents
- Update procedures
- Review best practices
- Update thresholds 