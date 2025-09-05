import json
import os
import psycopg2
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    AWS Lambda function to update device heartbeat in device_state table
    
    Expected event format:
    {
        "device_id": "device123",
        "site_id": "site456",
        "status": "ready",  # optional: ready, degraded, error
        "agent_version": "1.2.3",  # optional
        "cpu_pct": 45.2,  # optional
        "disk_free_gb": 128.5,  # optional
        "queue_depth": 10,  # optional
        "poll_interval_s": 30  # optional
    }
    
    Or for multiple devices:
    {
        "devices": [
            {"device_id": "hvac-001", "site_id": "building-a", "status": "ready"},
            {"device_id": "hvac-002", "site_id": "building-a", "status": "ready"}
        ]
    }
    """
    
    try:
        # Get database connection parameters from environment variables
        db_host = os.environ['DB_HOST']
        db_port = os.environ.get('DB_PORT', '5432')
        db_name = os.environ['DB_NAME']
        db_user = os.environ['DB_USER']
        db_password = os.environ['DB_PASSWORD']
        
        # Handle both single device and multiple devices
        devices_to_update = []
        
        if 'devices' in event:
            # Multiple devices format
            devices_to_update = event['devices']
        else:
            # Single device format
            device_id = event.get('device_id')
            site_id = event.get('site_id')
            
            if not device_id or not site_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'device_id and site_id are required'
                    })
                }
            
            devices_to_update = [event]
        
        # Connect to database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )
        
        updated_devices = []
        
        with conn.cursor() as cursor:
            for device_data in devices_to_update:
                device_id = device_data.get('device_id')
                site_id = device_data.get('site_id')
                
                if not device_id or not site_id:
                    logger.warning(f"Skipping device with missing device_id or site_id: {device_data}")
                    continue
                
                # Optional fields
                status = device_data.get('status')
                agent_version = device_data.get('agent_version')
                cpu_pct = device_data.get('cpu_pct')
                disk_free_gb = device_data.get('disk_free_gb')
                queue_depth = device_data.get('queue_depth')
                poll_interval_s = device_data.get('poll_interval_s')
                last_upload_ts = device_data.get('last_upload_ts')
                
                # Use UPSERT (INSERT ... ON CONFLICT) to handle both new and existing devices
                upsert_sql = """
                    INSERT INTO device_state (
                        device_id, site_id, last_seen_ts, status, agent_version, 
                        cpu_pct, disk_free_gb, queue_depth, poll_interval_s, 
                        last_upload_ts, updated_at
                    ) VALUES (
                        %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    ON CONFLICT (device_id) 
                    DO UPDATE SET
                        last_seen_ts = NOW(),
                        status = COALESCE(EXCLUDED.status, device_state.status),
                        agent_version = COALESCE(EXCLUDED.agent_version, device_state.agent_version),
                        cpu_pct = COALESCE(EXCLUDED.cpu_pct, device_state.cpu_pct),
                        disk_free_gb = COALESCE(EXCLUDED.disk_free_gb, device_state.disk_free_gb),
                        queue_depth = COALESCE(EXCLUDED.queue_depth, device_state.queue_depth),
                        poll_interval_s = COALESCE(EXCLUDED.poll_interval_s, device_state.poll_interval_s),
                        last_upload_ts = COALESCE(EXCLUDED.last_upload_ts, device_state.last_upload_ts),
                        updated_at = NOW()
                """
                
                cursor.execute(upsert_sql, (
                    device_id, site_id, status, agent_version, 
                    cpu_pct, disk_free_gb, queue_depth, poll_interval_s, last_upload_ts
                ))
                
                updated_devices.append(device_id)
                logger.info(f"Updated heartbeat for device {device_id}")
            
            conn.commit()
        
        conn.close()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Heartbeat updated for {len(updated_devices)} device(s)',
                'updated_devices': updated_devices,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
    except psycopg2.Error as db_error:
        logger.error(f"Database error: {str(db_error)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Database error',
                'message': str(db_error)
            })
        }
        
    except Exception as e:
        logger.error(f"Error updating heartbeat: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }

# For local testing
if __name__ == "__main__":
    # Set up test environment variables
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_NAME'] = 'hvac_db'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_PASSWORD'] = 'password'
    
    # Test single device
    test_event_single = {
        "device_id": "hvac-unit-001",
        "site_id": "building-a",
        "status": "ready",
        "agent_version": "1.0.0",
        "cpu_pct": 25.5,
        "disk_free_gb": 45.2
    }
    
    # Test multiple devices
    test_event_multiple = {
        "devices": [
            {"device_id": "hvac-001", "site_id": "building-a", "status": "ready", "cpu_pct": 15.2},
            {"device_id": "hvac-002", "site_id": "building-a", "status": "ready", "cpu_pct": 22.1},
            {"device_id": "hvac-003", "site_id": "building-b", "status": "degraded", "cpu_pct": 85.5}
        ]
    }
    
    print("Testing single device:")
    result = lambda_handler(test_event_single, None)
    print(json.dumps(result, indent=2))
    
    print("\nTesting multiple devices:")
    result = lambda_handler(test_event_multiple, None)
    print(json.dumps(result, indent=2))
