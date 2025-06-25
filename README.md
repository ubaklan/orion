```shell
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To run the process
```shell
python3 scraper.py --batches_per_second 0.01 --batch_size 200 --interface en0 --max-concurrent 300
```