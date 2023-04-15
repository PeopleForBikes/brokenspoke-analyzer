PFB Bicycle Network Analysis
============================

The `Bicycle Network Analysis (BNA) <https://github.com/azavea/pfb-network-connectivity/tree/develop/src/analysis>`_ 
is a data analysis tool that measures how well 
bike networks connect people with the places they want to go. It is 
implemented in `PostgreSQL <https://www.postgresql.org/>`_ using 
the `PostGIS <https://postgis.net/>`_ spatial extension. A series of shell 
scripts, running inside a `Docker <https://docs.docker.com/get-started/>`_ 
container, are used to build the database and run the analysis.


BNA container setup for development
-----------------------------------

To develop the BNA, setup a development container by following these steps:

1. Fork the `azavea/pfb-network-connectivity <https://github.com/azavea/pfb-network-connectivity>`_ repository.

2. Do SQL/Shell development on your fork. For more details  on
   which SQL/Shell files implement the BNA see :ref:`bna-control-flow`.

3. Build the docker image using the ``Dockerfile`` in your fork by running the following from the `src` folder of your fork::

	docker buildx build -t azavea/pfb-network-connectivity:0.16.1 -f analysis/Dockerfile .

   Note that you can use any other name besides `azavea/pfb-network-connectivity:0.16.1` 

4. Rename the built image from step 3, if desired::

	docker tag azavea/pfb-network-connectivity:0.16.1 your_username/bna:0.0

.. _bna-control-flow:

Control flow of the BNA
-----------------------

.. graphviz::

   digraph {
      bgcolor="#fcfaf6";
	  node [shape="box", style="rounded"];
      {rank = same; "entrypoint.sh"}
	  {rank = same; "run_analysis.sh"}
	  {rank = same; "import.sh" "run_connectivity.sh" "export_connectivity.sh"}
	  {rank = same; "import/import_neighborhood.sh" "import/import_jobs.sh" "import/import_osm.sh"}
	  {rank = same; "prepare_tables.sql" "clip_osm.sql" "features/*.sql" "stress/*.sql"}
	  {rank = same; "connectivity/*.sql" "connectivity/destinations/*.sql"}
	  "entrypoint.sh" -> "run_analysis.sh"; 
	  "run_analysis.sh" -> "import.sh";
	  "import.sh" -> "run_connectivity.sh" -> "export_connectivity.sh";
	  "import.sh" -> "import/import_neighborhood.sh" -> "import/import_jobs.sh" -> "import/import_osm.sh";
	  "import/import_osm.sh" -> "prepare_tables.sql" -> "clip_osm.sql" -> "features/*.sql" -> "stress/*.sql"
	  "run_connectivity.sh" -> "connectivity/*.sql" -> "connectivity/destinations/*.sql" ;
   }

.. note::
   The PostgreSQL Docker image will run automatically scripts found in /docker-entrypoint-initdb.d/ So 
   setup_database.sh, which is not shown in the control flow figure, will run automatically. 


.. _bna-brokenspoke-analyzer:

Running the BNA using the Brokenspoke-analyzer tool
---------------------------------------------------

Ensure you have the latest (global) pip::

	pip install --upgrade pip

Install `poetry <https://python-poetry.org/>`_ for packaging and dependency management::

	pip install poetry

Or upgrade to latest version if already installed::

	pip install poetry --upgrade

Fork `brokenspoke-analyzer <https://github.com/PeopleForBikes/brokenspoke-analyzer>`_ 
into your account. Clone your fork for local development::

	git clone git@github.com:your_username/brokenspoke-analyzer.git

``cd`` into ``brokenspoke-analyzer`` and to create a new Python virtual environment 
(inside the project, given the poetry config file) run::

	poetry shell

Then, to install dependencies needed for project, run::

	poetry install

Finally, to exit the virtual environment created by poetry, run::

	exit

To run the modified BNA for a city in the US, for example Flagstaff, AZ, run::
	
	poetry run bna run arizona flagstaff


