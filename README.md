# HVAC Heartbeat Lambda Function

This AWS Lambda function updates device heartbeat information in your HVAC database's `device_state` table. It's designed to work with your TimescaleDB schema and can handle both single device updates and batch updates for multiple devices.

## Features

- ✅ Updates `last_seen_ts` timestamp for device heartbeats
- ✅ Supports both single device and multiple device updates
- ✅ UPSERT functionality (creates new records or updates existing ones)
- ✅ Optional device metrics (CPU, disk space, status, etc.)
- ✅ Comprehensive error handling and logging
- ✅ Works with your existing `v_devices_stale` view

## Files

- `lambda_function.py` - Main Lambda function code
- `requirements.txt` - Python dependencies
- `deploy.sh` - Deployment script for AWS
- `README.md` - This documentation

## Quick Start

### 1. Prerequisites

- AWS CLI installed and configured
- Python 3.9+ 
- Access to your RDS PostgreSQL/TimescaleDB instance
- Lambda execution role with appropriate permissions

### 2. Deploy to AWS

```bash
# Make the deployment script executable
chmod +x deploy.sh

# Update the configuration in deploy.sh:
# - FUNCTION_NAME
# - REGION  
# - ROLE_ARN

# Deploy
./deploy.sh
```

### 3. Configure Environment Variables

In the AWS Lambda console, set these environment variables:

```
DB_HOST=your-rds-endpoint.amazonaws.com
DB_PORT=5432
DB_NAME=hvac_db
DB_USER=your_username
DB_PASSWORD=your_secure_password
```

### 4. Test the Function

Use these sample events to test:

**Single Device:**
```json
{
  "device_id": "hvac-unit-001",
  "site_id": "building-a",
  "status": "ready",
  "agent_version": "1.0.0",
  "cpu_pct": 25.5,
  "disk_free_gb": 45.2
}
```

**Multiple Devices:**
```json
{
  "devices": [
    {"device_id": "hvac-001", "site_id": "building-a", "status": "ready"},
    {"device_id": "hvac-002", "site_id": "building-a", "status": "ready"},
    {"device_id": "hvac-003", "site_id": "building-b", "status": "degraded"}
  ]
}
```

## Event Format

### Single Device Update

```json
{
  "device_id": "string (required)",
  "site_id": "string (required)", 
  "status": "ready|degraded|error (optional)",
  "agent_version": "string (optional)",
  "cpu_pct": "float (optional)",
  "disk_free_gb": "float (optional)",
  "queue_depth": "integer (optional)",
  "poll_interval_s": "integer (optional)",
  "last_upload_ts": "timestamp (optional)"
}
```

### Multiple Device Update

```json
{
  "devices": [
    {
      "device_id": "string (required)",
      "site_id": "string (required)",
      // ... other optional fields
    }
  ]
}
```

## Scheduling Options

### Option 1: EventBridge (CloudWatch Events)

Create a rule to trigger every minute (minimum interval):

```bash
aws events put-rule \
    --name hvac-heartbeat-schedule \
    --schedule-expression "rate(1 minute)"

aws events put-targets \
    --rule hvac-heartbeat-schedule \
    --targets "Id"="1","Arn"="arn:aws:lambda:region:account:function:hvac-heartbeat-updater"
```

### Option 2: API Gateway + Device Calls

Set up API Gateway to allow devices to call the Lambda directly:

```bash
# Devices POST to: https://api-id.execute-api.region.amazonaws.com/prod/heartbeat
```

### Option 3: IoT Core Integration

For IoT devices, integrate with AWS IoT Core for automatic triggering.

## Database Schema Compatibility

This function works with your existing schema:

```sql
-- Your device_state table
CREATE TABLE device_state (
    device_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    last_seen_ts TIMESTAMP WITH TIME ZONE NOT NULL,
    last_upload_ts TIMESTAMP WITH TIME ZONE,
    queue_depth INTEGER,
    agent_version TEXT,
    poll_interval_s INTEGER,
    cpu_pct FLOAT,
    disk_free_gb FLOAT,
    status TEXT CHECK (status IN ('ready','degraded','error')),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Your stale devices view
CREATE OR REPLACE VIEW v_devices_stale AS
SELECT device_id, site_id, last_seen_ts, now() - last_seen_ts AS age
FROM device_state
WHERE now() - last_seen_ts > interval '120 seconds';
```

## Monitoring Stale Devices

Query stale devices using your existing view:

```sql
-- Get all stale devices
SELECT * FROM v_devices_stale;

-- Count stale devices by site
SELECT site_id, COUNT(*) as stale_count 
FROM v_devices_stale 
GROUP BY site_id;

-- Get devices offline for more than 5 minutes
SELECT device_id, site_id, age 
FROM v_devices_stale 
WHERE age > interval '5 minutes';
```

## IAM Permissions

Your Lambda execution role needs these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream", 
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:CreateNetworkInterface",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DeleteNetworkInterface"
            ],
            "Resource": "*"
        }
    ]
}
```

## VPC Configuration

If your RDS instance is in a VPC:

1. Configure Lambda to use the same VPC
2. Use private subnets with NAT Gateway for internet access
3. Security group must allow outbound traffic to RDS port (5432)
4. RDS security group must allow inbound from Lambda security group

## Local Testing

```bash
# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=hvac_db
export DB_USER=postgres
export DB_PASSWORD=password

# Run locally
python lambda_function.py
```

## Troubleshooting

### Common Issues

1. **Connection timeout**: Check VPC/security group configuration
2. **Authentication failed**: Verify DB credentials in environment variables
3. **Table doesn't exist**: Ensure Alembic migrations have been run
4. **Lambda timeout**: Increase timeout setting (default: 30 seconds)

### Logs

Check CloudWatch Logs for detailed error messages:

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/hvac-heartbeat"
```

## Performance Considerations

- **Batch Updates**: Use multiple devices format for better performance
- **Connection Pooling**: Consider using RDS Proxy for high-frequency updates
- **Timeout**: Adjust Lambda timeout based on batch size
- **Memory**: 128MB is sufficient for most use cases

## Cost Optimization

- Use EventBridge for scheduled execution (cheaper than continuous polling)
- Batch multiple device updates in single invocation
- Consider RDS Proxy to reduce connection overhead
- Monitor CloudWatch metrics for optimization opportunities

## Security Best Practices

- Store database credentials in AWS Secrets Manager
- Use VPC endpoints to avoid internet traffic
- Enable encryption in transit for RDS connections
- Rotate database credentials regularly
- Use least-privilege IAM policies
