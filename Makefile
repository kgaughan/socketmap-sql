wheel:
	rm -rf build
	python3 setup.py sdist bdist_wheel

upload: wheel
	twine upload dist/socketmap_sql-*

clean:
	rm -rf build dist *.egg-info

.PHONY: wheel upload clean
