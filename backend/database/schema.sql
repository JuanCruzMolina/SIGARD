--
-- PostgreSQL database dump
--

-- Dumped from database version 16.4 (Debian 16.4-1.pgdg110+2)
-- Dumped by pg_dump version 16.4 (Debian 16.4-1.pgdg110+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: pg_database_owner
--

CREATE SCHEMA public;


ALTER SCHEMA public OWNER TO pg_database_owner;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: pg_database_owner
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alertas; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.alertas (
    id integer NOT NULL,
    titulo character varying(200) NOT NULL,
    descripcion text,
    nivel character varying(10),
    barrio_id integer,
    activa boolean DEFAULT true,
    creada_por integer,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT alertas_nivel_check CHECK (((nivel)::text = ANY ((ARRAY['alto'::character varying, 'medio'::character varying, 'bajo'::character varying])::text[])))
);


ALTER TABLE public.alertas OWNER TO sigard_user;

--
-- Name: alertas_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.alertas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.alertas_id_seq OWNER TO sigard_user;

--
-- Name: alertas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.alertas_id_seq OWNED BY public.alertas.id;


--
-- Name: barrios; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.barrios (
    id integer NOT NULL,
    nombre character varying(100) NOT NULL,
    radio_censal character varying(20),
    poblacion integer,
    geom public.geometry(Polygon,4326)
);


ALTER TABLE public.barrios OWNER TO sigard_user;

--
-- Name: barrios_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.barrios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.barrios_id_seq OWNER TO sigard_user;

--
-- Name: barrios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.barrios_id_seq OWNED BY public.barrios.id;


--
-- Name: casos_dengue; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.casos_dengue (
    id integer NOT NULL,
    fecha_inicio_sintomas date,
    fecha_confirmacion date NOT NULL,
    barrio_id integer,
    latitud double precision,
    longitud double precision,
    serotipo integer,
    anonimizado boolean DEFAULT true,
    geom public.geometry(Point,4326),
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT casos_dengue_serotipo_check CHECK ((serotipo = ANY (ARRAY[1, 2, 3, 4])))
);


ALTER TABLE public.casos_dengue OWNER TO sigard_user;

--
-- Name: casos_dengue_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.casos_dengue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.casos_dengue_id_seq OWNER TO sigard_user;

--
-- Name: casos_dengue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.casos_dengue_id_seq OWNED BY public.casos_dengue.id;


--
-- Name: clima_diario; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.clima_diario (
    id integer NOT NULL,
    fecha date NOT NULL,
    temp_min double precision,
    temp_max double precision,
    temp_media double precision,
    humedad_relativa double precision,
    precipitaciones double precision,
    fuente character varying(50) DEFAULT 'SMN'::character varying
);


ALTER TABLE public.clima_diario OWNER TO sigard_user;

--
-- Name: clima_diario_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.clima_diario_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.clima_diario_id_seq OWNER TO sigard_user;

--
-- Name: clima_diario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.clima_diario_id_seq OWNED BY public.clima_diario.id;


--
-- Name: usuarios; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.usuarios (
    id integer NOT NULL,
    email character varying(150) NOT NULL,
    password_hash character varying(255) NOT NULL,
    rol character varying(20) DEFAULT 'user'::character varying,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT usuarios_rol_check CHECK (((rol)::text = ANY ((ARRAY['admin'::character varying, 'user'::character varying])::text[])))
);


ALTER TABLE public.usuarios OWNER TO sigard_user;

--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.usuarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.usuarios_id_seq OWNER TO sigard_user;

--
-- Name: usuarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.usuarios_id_seq OWNED BY public.usuarios.id;


--
-- Name: zonas_riesgo; Type: TABLE; Schema: public; Owner: sigard_user
--

CREATE TABLE public.zonas_riesgo (
    id integer NOT NULL,
    fecha_prediccion date NOT NULL,
    barrio_id integer,
    nivel_riesgo character varying(10),
    probabilidad double precision,
    algoritmo character varying(50),
    geom public.geometry(Polygon,4326),
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT zonas_riesgo_nivel_riesgo_check CHECK (((nivel_riesgo)::text = ANY ((ARRAY['alto'::character varying, 'medio'::character varying, 'bajo'::character varying])::text[]))),
    CONSTRAINT zonas_riesgo_probabilidad_check CHECK (((probabilidad >= (0)::double precision) AND (probabilidad <= (1)::double precision)))
);


ALTER TABLE public.zonas_riesgo OWNER TO sigard_user;

--
-- Name: zonas_riesgo_id_seq; Type: SEQUENCE; Schema: public; Owner: sigard_user
--

CREATE SEQUENCE public.zonas_riesgo_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.zonas_riesgo_id_seq OWNER TO sigard_user;

--
-- Name: zonas_riesgo_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sigard_user
--

ALTER SEQUENCE public.zonas_riesgo_id_seq OWNED BY public.zonas_riesgo.id;


--
-- Name: alertas id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.alertas ALTER COLUMN id SET DEFAULT nextval('public.alertas_id_seq'::regclass);


--
-- Name: barrios id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.barrios ALTER COLUMN id SET DEFAULT nextval('public.barrios_id_seq'::regclass);


--
-- Name: casos_dengue id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.casos_dengue ALTER COLUMN id SET DEFAULT nextval('public.casos_dengue_id_seq'::regclass);


--
-- Name: clima_diario id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.clima_diario ALTER COLUMN id SET DEFAULT nextval('public.clima_diario_id_seq'::regclass);


--
-- Name: usuarios id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.usuarios ALTER COLUMN id SET DEFAULT nextval('public.usuarios_id_seq'::regclass);


--
-- Name: zonas_riesgo id; Type: DEFAULT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.zonas_riesgo ALTER COLUMN id SET DEFAULT nextval('public.zonas_riesgo_id_seq'::regclass);


--
-- Name: alertas alertas_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_pkey PRIMARY KEY (id);


--
-- Name: barrios barrios_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.barrios
    ADD CONSTRAINT barrios_pkey PRIMARY KEY (id);


--
-- Name: casos_dengue casos_dengue_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.casos_dengue
    ADD CONSTRAINT casos_dengue_pkey PRIMARY KEY (id);


--
-- Name: clima_diario clima_diario_fecha_key; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.clima_diario
    ADD CONSTRAINT clima_diario_fecha_key UNIQUE (fecha);


--
-- Name: clima_diario clima_diario_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.clima_diario
    ADD CONSTRAINT clima_diario_pkey PRIMARY KEY (id);


--
-- Name: usuarios usuarios_email_key; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_email_key UNIQUE (email);


--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);


--
-- Name: zonas_riesgo zonas_riesgo_pkey; Type: CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.zonas_riesgo
    ADD CONSTRAINT zonas_riesgo_pkey PRIMARY KEY (id);


--
-- Name: alertas alertas_barrio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_barrio_id_fkey FOREIGN KEY (barrio_id) REFERENCES public.barrios(id);


--
-- Name: alertas alertas_creada_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_creada_por_fkey FOREIGN KEY (creada_por) REFERENCES public.usuarios(id);


--
-- Name: casos_dengue casos_dengue_barrio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.casos_dengue
    ADD CONSTRAINT casos_dengue_barrio_id_fkey FOREIGN KEY (barrio_id) REFERENCES public.barrios(id);


--
-- Name: zonas_riesgo zonas_riesgo_barrio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: sigard_user
--

ALTER TABLE ONLY public.zonas_riesgo
    ADD CONSTRAINT zonas_riesgo_barrio_id_fkey FOREIGN KEY (barrio_id) REFERENCES public.barrios(id);


--
-- PostgreSQL database dump complete
--

