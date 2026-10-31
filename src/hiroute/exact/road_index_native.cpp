// Exact integer-scaled version of RoadIndex. No binary64 routing arithmetic.
// Each metric is multiplied by the LCM of ALL of its rational denominators.
// This is exact, may use arbitrarily large integers, and is preprocessing work.
#include <boost/multiprecision/cpp_int.hpp>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <list>
#include <memory>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using boost::multiprecision::cpp_int;
using Clock = std::chrono::steady_clock;
using Check = int (*)();
static thread_local std::string failure;
static void checkpoint(Check check) { if (check && !check()) throw std::runtime_error("resource_check"); }
static double seconds(Clock::time_point start) { return std::chrono::duration<double>(Clock::now()-start).count(); }
static cpp_int gcd(cpp_int a, cpp_int b) { while(b != 0) { cpp_int r=a%b; a=std::move(b); b=std::move(r); } return a; }
static cpp_int lcm(const cpp_int&a,const cpp_int&b) { return (a/gcd(a,b))*b; }
struct Rational { cpp_int n,d; };
static Rational rational(const std::string& text) {
 auto slash=text.find('/'); auto valid=[](const std::string&s){return !s.empty()&&(s.size()==1||s[0]!='0')&&std::all_of(s.begin(),s.end(),[](char c){return c>='0'&&c<='9';});};
 std::string ns=text.substr(0,slash), ds=slash==std::string::npos?"1":text.substr(slash+1);
 if(!valid(ns)||!valid(ds))throw std::runtime_error("TSV weights must be positive integer or numerator/denominator strings");
 cpp_int n(ns),d(ds); if(n<=0||d<=0)throw std::runtime_error("Road weights must be positive");
 cpp_int g=gcd(n,d); return {n/g,d/g};
}
static std::string number(const cpp_int& n,const cpp_int& d) { if(n==0)return "0"; cpp_int g=gcd(n,d); cpp_int a=n/g,b=d/g;return a.str()+(b==1?"":"/"+b.str()); }
static std::string quote(const std::string& text) { std::string out="\"";for(unsigned char c:text){if(c=='\\'||c=='\"'){out+='\\';out+=char(c);}else if(c<32)throw std::runtime_error("Control characters in road identifiers");else out+=char(c);}return out+'\"'; }
static std::vector<std::string> fields(const std::string& line) { std::vector<std::string> out;size_t p=0;for(int k=0;k<4;k++){size_t q=line.find('\t',p);if(q==std::string::npos)throw std::runtime_error("Malformed road TSV row");out.push_back(line.substr(p,q-p));p=q+1;}out.push_back(line.substr(p));for(auto&s:out)if(s.empty())throw std::runtime_error("Empty road TSV field");return out; }
struct Edge { uint32_t source,target;std::string id;cpp_int time,length; };
struct Item { cpp_int distance;uint32_t node; };
struct Greater { bool operator()(const Item&a,const Item&b)const{return a.distance>b.distance||(a.distance==b.distance&&a.node>b.node);} };
struct Tree { bool reverse,length;uint32_t root;std::vector<cpp_int> distance;std::vector<uint8_t> known,settled;std::priority_queue<Item,std::vector<Item>,Greater> queue;Tree(bool r,bool l,uint32_t rt,size_t n):reverse(r),length(l),root(rt),distance(n),known(n,0),settled(n,0){distance[root]=0;known[root]=1;queue.push({0,root});} };
struct Graph {
 std::vector<std::string> nodes;std::unordered_map<std::string,uint32_t> node_ids;
 std::vector<Edge> edges;cpp_int time_scale=1,length_scale=1;
 std::vector<uint64_t> forward_offset,reverse_offset;std::vector<uint32_t> forward_edges,reverse_edges;
 std::list<std::unique_ptr<Tree>> trees;size_t cache_size;std::string result;
 uint64_t scalar_queries=0,cache_hits=0,settled_vertices=0,leg_queries=0;double build_seconds=0,scalar_seconds=0,leg_seconds=0;
 uint32_t intern(const std::string& s){auto it=node_ids.find(s);if(it!=node_ids.end())return it->second;if(nodes.size()>=UINT32_MAX)throw std::runtime_error("Road vertex count exceeds index representation");uint32_t id=uint32_t(nodes.size());nodes.push_back(s);node_ids.emplace(s,id);return id;}
 Graph(const std::string&path,size_t caches,Check check):cache_size(caches){
  auto start=Clock::now();std::ifstream input(path);if(!input)throw std::runtime_error("Cannot read road TSV");std::string line;uint64_t count=0;
  // Count before reserving so a multi-million-edge vector never temporarily
  // doubles its large exact-weight storage. This pass is cold preparation.
  while(std::getline(input,line)){if(count%4096==0)checkpoint(check);count++;}
  if(count>=UINT32_MAX)throw std::runtime_error("Road edge count exceeds index representation");
  edges.reserve(size_t(count));
  // A size hint only: reallocation remains legal for every graph shape.
  nodes.reserve(size_t(count/2+count/10+1));node_ids.reserve(size_t(count/2+count/10+1));
  input.clear();input.seekg(0);count=0;
  while(std::getline(input,line)){if(count%1024==0)checkpoint(check);auto f=fields(line);if(edges.size()>=UINT32_MAX)throw std::runtime_error("Road edge count exceeds index representation");uint32_t source=intern(f[0]),target=intern(f[1]);auto t=rational(f[3]),l=rational(f[4]);time_scale=lcm(time_scale,t.d);length_scale=lcm(length_scale,l.d);edges.push_back({source,target,std::move(f[2]),0,0});count++;}
  // Validate unique IDs by sorting pointers into the already-reserved edge
  // storage; do not duplicate millions of ID strings in an unordered_set.
  std::vector<const std::string*> identities;identities.reserve(edges.size());
  for(size_t k=0;k<edges.size();k++){if(k%4096==0)checkpoint(check);identities.push_back(&edges[k].id);}
  checkpoint(check);std::sort(identities.begin(),identities.end(),[](const std::string*a,const std::string*b){return *a<*b;});checkpoint(check);
  for(size_t k=1;k<identities.size();k++){if(k%4096==0)checkpoint(check);if(*identities[k-1]==*identities[k])throw std::runtime_error("Directed edge IDs must be unique");}
  identities.clear();identities.shrink_to_fit();input.clear();input.seekg(0);count=0;
  while(std::getline(input,line)){if(count%1024==0)checkpoint(check);auto f=fields(line);auto t=rational(f[3]),l=rational(f[4]);if(count>=edges.size()||edges[count].id!=f[2]||nodes[edges[count].source]!=f[0]||nodes[edges[count].target]!=f[1])throw std::runtime_error("Road TSV changed during index build");if(time_scale%t.d!=0||length_scale%l.d!=0)throw std::runtime_error("Road weights changed during index build");edges[count].time=t.n*(time_scale/t.d);edges[count].length=l.n*(length_scale/l.d);count++;}
  if(count!=edges.size())throw std::runtime_error("Road TSV changed during index build");
  forward_offset.resize(nodes.size()+1,0);reverse_offset.resize(nodes.size()+1,0);forward_edges.resize(edges.size());reverse_edges.resize(edges.size());
  for(size_t k=0;k<edges.size();k++){if(k%4096==0)checkpoint(check);forward_offset[edges[k].source+1]++;reverse_offset[edges[k].target+1]++;}
  for(size_t k=1;k<forward_offset.size();k++){forward_offset[k]+=forward_offset[k-1];reverse_offset[k]+=reverse_offset[k-1];}
  auto fpos=forward_offset,rpos=reverse_offset;for(size_t k=0;k<edges.size();k++){if(k%4096==0)checkpoint(check);forward_edges[fpos[edges[k].source]++]=uint32_t(k);reverse_edges[rpos[edges[k].target]++]=uint32_t(k);}
  build_seconds=seconds(start);checkpoint(check);
 }
 std::unique_ptr<Tree> ephemeral;
 Tree& tree(uint32_t root,bool reverse,bool length,Check check,uint32_t stop=UINT32_MAX){
  checkpoint(check);scalar_queries++;Tree* active=nullptr;
  for(auto it=trees.begin();it!=trees.end();++it)if((*it)->root==root&&(*it)->reverse==reverse&&(*it)->length==length){cache_hits++;active=it->get();trees.splice(trees.begin(),trees,it);break;}
  if(!active){auto made=std::make_unique<Tree>(reverse,length,root,nodes.size());active=made.get();if(cache_size){trees.push_front(std::move(made));while(trees.size()>cache_size)trees.pop_back();}else ephemeral=std::move(made);}
  if(stop!=UINT32_MAX&&active->settled[stop])return *active;
  auto start=Clock::now();auto&offset=reverse?reverse_offset:forward_offset;auto&adj=reverse?reverse_edges:forward_edges;uint64_t work=0;
  while(!active->queue.empty()){
   Item item=active->queue.top();active->queue.pop();uint32_t u=item.node;if(active->settled[u]||item.distance!=active->distance[u])continue;active->settled[u]=1;settled_vertices++;
   if(settled_vertices%256==0)checkpoint(check);
   for(uint64_t k=offset[u];k<offset[u+1];k++){if(++work%1024==0)checkpoint(check);auto&e=edges[adj[k]];uint32_t v=reverse?e.source:e.target;cpp_int nd=item.distance+(length?e.length:e.time);if(!active->known[v]||nd<active->distance[v]){active->known[v]=1;active->distance[v]=nd;active->queue.push({std::move(nd),v});}}
   if(u==stop)break;
  }
  scalar_seconds+=seconds(start);checkpoint(check);return *active;
 }
 std::string leg(const std::string&source,const std::string&target,Check check){
  auto start=Clock::now();leg_queries++;if(source==target)return "{\"source\":"+quote(source)+",\"target\":"+quote(target)+",\"time_s\":\"0\",\"length_m\":\"0\",\"edges\":[]}";
  auto si=node_ids.find(source),ti=node_ids.find(target);if(si==node_ids.end()||ti==node_ids.end())return "null";uint32_t u=si->second,z=ti->second;Tree&t=tree(z,true,false,check,u);if(!t.settled[u]){leg_seconds+=seconds(start);return "null";}
  cpp_int total_length=0;std::string out="{\"source\":"+quote(source)+",\"target\":"+quote(target)+",\"time_s\":"+quote(number(t.distance[u],time_scale))+",\"edges\":[";bool first=true;
  while(u!=z){checkpoint(check);uint32_t best=UINT32_MAX;for(uint64_t k=forward_offset[u];k<forward_offset[u+1];k++){uint32_t eid=forward_edges[k];auto&e=edges[eid];if(!t.settled[e.target]||e.time+t.distance[e.target]!=t.distance[u])continue;if(best==UINT32_MAX||nodes[e.target]<nodes[edges[best].target]||(e.target==edges[best].target&&e.id<edges[best].id))best=eid;}
   if(best==UINT32_MAX)throw std::runtime_error("Missing exact shortest-path DAG successor");auto&e=edges[best];if(!first)out+=',';first=false;out+="{\"source\":"+quote(nodes[e.source])+",\"target\":"+quote(nodes[e.target])+",\"edge_id\":"+quote(e.id)+",\"time_s\":"+quote(number(e.time,time_scale))+",\"length_m\":"+quote(number(e.length,length_scale))+"}";total_length+=e.length;u=e.target;
  }
  out+="],\"length_m\":"+quote(number(total_length,length_scale))+"}";leg_seconds+=seconds(start);return out;
 }
 std::string distances(const std::string&anchor,bool reverse,bool length,const std::string& exposed,Check check){
  auto ai=node_ids.find(anchor);Tree*t=ai==node_ids.end()?nullptr:&tree(ai->second,reverse,length,check);std::istringstream names(exposed);std::string name,out="{";bool first=true;while(std::getline(names,name)){checkpoint(check);auto it=node_ids.find(name);if(name==anchor||(t&&it!=node_ids.end()&&t->settled[it->second])){if(!first)out+=',';first=false;out+=quote(name)+":"+quote(name==anchor?"0":number(t->distance[it->second],length?length_scale:time_scale));}}return out+"}";
 }
 std::string metrics(){size_t values=0,queued=0;for(auto&t:trees){values+=t->distance.size();queued+=t->queue.size();}std::ostringstream out;out<<"{\"index_builds\":1,\"nodes\":"<<nodes.size()<<",\"edges\":"<<edges.size()<<",\"build_time_s\":"<<build_seconds<<",\"scalar_queries\":"<<scalar_queries<<",\"scalar_cache_hits\":"<<cache_hits<<",\"scalar_settled_vertices\":"<<settled_vertices<<",\"selected_leg_queries\":"<<leg_queries<<",\"scalar_time_s\":"<<scalar_seconds<<",\"selected_leg_time_s\":"<<leg_seconds<<",\"distance_cache_entries\":"<<trees.size()<<",\"distance_cache_values\":"<<values<<",\"queued_labels\":"<<queued<<",\"time_scale\":"<<quote(time_scale.str())<<",\"length_scale\":"<<quote(length_scale.str())<<"}";return out.str();}
};
extern "C" {
 void* hiroute_road_create(const char*path,int cache_count,Check check){try{if(cache_count<0)throw std::runtime_error("Negative cache count");failure.clear();return new Graph(path,size_t(cache_count),check);}catch(const std::exception&e){failure=e.what();return nullptr;}}
 void hiroute_road_free(void*ptr){delete static_cast<Graph*>(ptr);}
 const char* hiroute_road_error(){return failure.c_str();}
 const char* hiroute_road_query(void*ptr,const char*kind,const char*anchor,const char*target,const char*weight,const char*exposed,Check check){try{failure.clear();if(!ptr)throw std::runtime_error("Closed road index");Graph&g=*static_cast<Graph*>(ptr);std::string k(kind),w(weight);if(k=="metrics")g.result=g.metrics();else if(k=="leg")g.result=g.leg(anchor,target,check);else if(k=="from"||k=="to"){if(w!="time_s"&&w!="length_m")throw std::runtime_error("Unknown road metric");g.result=g.distances(anchor,k=="to",w=="length_m",exposed,check);}else throw std::runtime_error("Unknown road query");return g.result.c_str();}catch(const std::exception&e){if(ptr){auto&g=*static_cast<Graph*>(ptr);g.trees.clear();g.ephemeral.reset();}failure=e.what();return nullptr;}}
}
