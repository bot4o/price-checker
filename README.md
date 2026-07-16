# Price Checker — web version
FastAPI backend with parallel async queries with certain sites.

## Installation 
```sh
git clone https://github.com/bot4o/price-checker
cd price-checker
```

## Starting (localy) 
```sh
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8090
```

## Starting (docker):
```sh
    docker build -t aks-price-checker .
    docker run -d -p 8090:8090 --name price-checker aks-price-checker
```
