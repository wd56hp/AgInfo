# Transferring ethonal.csv from Windows to Unraid Server

## Quick Instructions

### Option 1: Using SCP (Recommended if you have SSH access)

From Windows PowerShell or Command Prompt:

```powershell
scp "C:\Users\will.darrah\OneDrive - Darrah Oil\ethonal.csv" root@DOC-UNRAID-SERV:/mnt/user/appdata/AgInfo/db/temp/
```

Or if you have a different username:
```powershell
scp "C:\Users\will.darrah\OneDrive - Darrah Oil\ethonal.csv" username@DOC-UNRAID-SERV:/mnt/user/appdata/AgInfo/db/temp/
```

### Option 2: Using Network Share (SMB)

1. Open File Explorer on Windows
2. Navigate to: `\\DOC-UNRAID-SERV\[your-share-name]\appdata\AgInfo\db\temp\`
3. Copy `ethonal.csv` to that location

### Option 3: Using WinSCP or FileZilla

1. Connect to DOC-UNRAID-SERV via SFTP
2. Navigate to: `/mnt/user/appdata/AgInfo/db/temp/`
3. Upload `ethonal.csv`

### Option 4: Using the Helper Script

After transferring the file to any location on the server, run:

```bash
./db/tools/transfer_ethanol_csv.sh /path/to/ethonal.csv
```

## After Transfer

Once the file is in `/mnt/user/appdata/AgInfo/db/temp/ethonal.csv`, you can run:

```bash
# Dry run (preview what will be imported)
./db/tools/run_import_ethanol_plants.sh

# Actually import the data
./db/tools/run_import_ethanol_plants.sh --apply
```

Or specify the full path:

```bash
./db/tools/run_import_ethanol_plants.sh "/mnt/user/appdata/AgInfo/db/temp/ethonal.csv" --apply
```
