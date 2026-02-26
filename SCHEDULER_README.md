# Automated Portfolio Report Scheduler

## Overview

Your weekly portfolio report is now configured to run automatically every **Sunday at 9:00 AM** using macOS's launchd scheduler.

## What Was Set Up

### 1. Modified Files
- **weekly_report_gen.py**: Added `--no-open` command-line flag to skip auto-opening PDF when running scheduled

### 2. New Files Created
- **run_report.sh**: Wrapper script that:
  - Sources environment variables from ~/.zshrc
  - Activates virtual environment
  - Runs weekly_report_gen.py with --no-open flag
  - Logs execution with timestamps

- **~/Library/LaunchAgents/com.user.robinhood-report.plist**: launchd configuration that:
  - Schedules execution every Sunday at 9:00 AM
  - Captures stdout to `~/Library/Logs/robinhood-report.log`
  - Captures stderr to `~/Library/Logs/robinhood-report.error.log`

## How It Works

1. Every Sunday at 9:00 AM, launchd triggers the job
2. run_report.sh loads your API credentials from ~/.zshrc
3. The script generates the report without opening the PDF
4. Email is sent automatically (if configured)
5. Execution logs are saved for troubleshooting

## Management Commands

### Check Job Status
```bash
launchctl list | grep robinhood-report
```

### View Logs
```bash
# View execution log
tail -f ~/Library/Logs/robinhood-report.log

# View error log
tail -f ~/Library/Logs/robinhood-report.error.log

# View recent logs
tail -50 ~/Library/Logs/robinhood-report.log
```

### Manual Test Run
```bash
# Trigger immediate execution (for testing)
launchctl start com.user.robinhood-report

# Or test the wrapper script directly
cd /path/to/robinhood-report
./run_report.sh
```

### Disable Scheduled Execution
```bash
# Unload the job (stops automatic execution)
launchctl unload ~/Library/LaunchAgents/com.user.robinhood-report.plist
```

### Re-enable Scheduled Execution
```bash
# Reload the job (resumes automatic execution)
launchctl load ~/Library/LaunchAgents/com.user.robinhood-report.plist
```

### Modify Schedule
Edit the plist file at `~/Library/LaunchAgents/com.user.robinhood-report.plist`:
```bash
nano ~/Library/LaunchAgents/com.user.robinhood-report.plist
```

After making changes, reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.robinhood-report.plist
launchctl load ~/Library/LaunchAgents/com.user.robinhood-report.plist
```

**Schedule format in plist:**
- `Weekday`: 0=Sunday, 1=Monday, ..., 6=Saturday
- `Hour`: 0-23 (24-hour format)
- `Minute`: 0-59

## Manual Execution

You can still run reports manually:

```bash
# With PDF auto-open (interactive mode)
python3 weekly_report_gen.py

# Without PDF auto-open (scheduled mode)
python3 weekly_report_gen.py --no-open
```

## Troubleshooting

### Job Not Running?

1. **Check job is loaded:**
   ```bash
   launchctl list | grep robinhood-report
   ```
   Should show: `-	0	com.user.robinhood-report`

2. **Check logs for errors:**
   ```bash
   cat ~/Library/Logs/robinhood-report.error.log
   ```

3. **Test wrapper script manually:**
   ```bash
   cd /path/to/robinhood-report
   ./run_report.sh
   ```

4. **Verify environment variables:**
   - Ensure `ROBINHOOD_EMAIL`, `ROBINHOOD_PASSWORD`, `ANTHROPIC_API_KEY`, and `TAVILY_API_KEY` are set in `~/.zshrc`

### Common Issues

**"Permission denied" when running script:**
```bash
chmod +x /path/to/robinhood-report/run_report.sh
```

**Missing environment variables:**
- Check that ~/.zshrc contains all required variables
- Source ~/.zshrc or restart terminal

**Email not sending:**
- Verify SEND_EMAIL = True in weekly_report_gen.py
- Check email_sender.py is configured correctly

## File Locations

- **Wrapper Script**: `/path/to/robinhood-report/run_report.sh`
- **Launchd Config**: `~/Library/LaunchAgents/com.user.robinhood-report.plist`
- **Execution Log**: `~/Library/Logs/robinhood-report.log`
- **Error Log**: `~/Library/Logs/robinhood-report.error.log`
- **Generated PDFs**: `/path/to/robinhood-report/Portfolio_Reports/report_YYYY-MM-DD.pdf`

## Notes

- The job runs even if you're not logged in (as long as Mac is powered on and awake)
- Reports are saved in the `Portfolio_Reports/` directory with timestamp: `report_YYYY-MM-DD.pdf`
- The directory is automatically created if it doesn't exist
- Logs persist indefinitely for debugging
- The job is a user-level LaunchAgent (not system-wide)
