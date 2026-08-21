PYTHON ?= python3

.PHONY: test check-host dry-run analyze

test:
	$(PYTHON) -m unittest discover -s tests -v

check-host:
	./scripts/check_host.sh

dry-run:
	$(PYTHON) -m ssdbench.run_matrix \
		--config configs/workloads.json \
		--profile smoke \
		--target /dev/nvme0n1 \
		--condition page-gc75 \
		--mapping page \
		--gc-threshold 75 \
		--output results \
		--dry-run

analyze:
	$(PYTHON) -m ssdbench.analyze --input results --output results/report

