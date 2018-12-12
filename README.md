# Getting Started with NoSQL Databases for Spatial Analysis


## Contents

1. [Docker Intro](Docker_Intro.ipynb)
2. [MongoDB](MongoDB.ipynb)
3. [Neo4j](Neo4j.ipynb)
4. [Elasticsearch](Elasticsearch.ipynb)

---

## NoSQL Database Comparison

### MongoDB

**Type**: Document-based

**Summary**: MongoDB will likely feel particularly friendly for frontend developers, as the syntax for queries and administrative functions is strongly suggestive of JavaScript.  It supports a "schema on read" paradigm, which means it provides a lot of flexibility on how documents can be structured and how the data structure/data model can evolve over time.

**Transactional vs. Analytic<sup>1</sup>**: Transactional

**Recommended use**: Single-page or relatively simple applications. Particularly useful if your data model needs to be easily adaptable, and/or if you need to support many-to-one data relationships without much hassle.

**Spatial features**: Supports points, lines, and polygons.  Leverages familiar GeoJSON standards for geodata formatting.


### Neo4j

**Type**: Graph

**Summary**: Because Neo4j imposes a graph structure on your data, it requires some modeling effort at the outset to define your data in the context of nodes and relationships. It is not schemaless, but it has a much more flexible schema than relational databases.  It offers kind of a "happy medium" between document-based and relational databases.  Also implements a number of graph algorithms (ex: PageRank, shortest path, etc.) that can support niche research applications.

**Transactional vs. Analytic**: Analytic

**Recommended use**: Reasearch applications--especially those that can be framed as some kind of network analysis, and that can benefit from the availability of graph algorithms for analysis.

**Spatial features**: Supports points, lines, and polygons.  Leverages familiar GeoJSON standards for geodata formatting.


### Elasticsearch

**Type**: Document-based

**Summary**: Elasticsearch evolved as a solution to power large-scale archive/retrieve projects.  It is "schemaless", and applies a very robust approach to indexing and retrieval.  It has a strong feature set for natural language searches, with a range of built-in methods tailored specifically to text search (e.g. fuzzy searching, relevance scoring).  Spatial clauses can also be feathered into queries that take advantage Elasticsearch's advanced text search capabilities.

**Transactional vs. Analytic**: Analytic

**Recommended use**: Large volumes of time-series, log data, and/or text data that need to be stored and made easily searchable.  Could also be used as a metadata storage solution for multimedia files, raster imagery, etc. that are stored in a separate database.

**Spatial features**: Supports geo points and geo shapes (which can include points, lines, or polygons).  Very flexible when it comes to formatting: supports GeoJSON, well-known text (WKT), geohashes, and a number of other input formats. 


---

<sup>1</sup> See: Kleppmann, M. (2017) _Designing Data-Intensive Applications_, Ch 3. O'Reilly Media, Inc.