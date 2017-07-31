# yantra

### Setup
```sh
mkvirtualenv yantra
pip install -r requirements.txt
```

### Config
* set intercom and api.ai tokens in app.py
* setup aws credentials in local

### Deploy
```sh
zappa update dev
```

### Log
```sh
zappa tail dev
```